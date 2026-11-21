"""
wsi_scrubber.py – Binary IFD unlinking, binary header tag scrubbing, and metadata sanitization for WSI (NDPI).
"""

import os
import shutil
import struct
import json
from pathlib import Path
from openslide import OpenSlide
import tifffile
import numpy as np
import config


def unlink_macro_image_and_scrub(file_path: Path, make_backup: bool = True) -> bool:
    """
    De-identifies a Hamamatsu NDPI file:
      1. Overwrites Date/Time (Tag 306) and Scanner S/N in binary header.
      2. Unlinks the 'macro' image IFD from the TIFF IFD chain so viewers
         cannot extract the patient slide label or barcode.
    """
    file_path = Path(file_path)
    if make_backup:
        backup_path = file_path.with_suffix(".ndpi.bak")
        if not backup_path.exists():
            shutil.copy2(file_path, backup_path)
            print(f"  [WSI] Backup created: {backup_path.name}")

    # 1. Determine macro image dimensions via OpenSlide before editing
    macro_dims = None
    try:
        with OpenSlide(str(file_path)) as s:
            if "macro" in s.associated_images:
                macro_dims = s.associated_images["macro"].size  # (width, height)
    except Exception as e:
        print(f"  [WSI WARN] Could not pre-read macro size: {e}")

    # 2. Walk the TIFF IFD chain
    with open(file_path, "r+b") as f:
        header = f.read(4)
        if header[:2] == b"II":
            endian = "<"
        elif header[:2] == b"MM":
            endian = ">"
        else:
            raise ValueError(f"File {file_path.name} is not a valid TIFF/NDPI container.")

        # Read offset to first IFD (byte 4)
        first_ifd_offset = struct.unpack(f"{endian}I", f.read(4))[0]
        current_offset = first_ifd_offset
        prev_pointer_offset = 4

        while current_offset != 0:
            f.seek(current_offset)
            num_entries_bytes = f.read(2)
            if len(num_entries_bytes) < 2:
                break
            num_entries = struct.unpack(f"{endian}H", num_entries_bytes)[0]

            is_macro_ifd = False
            w, h = None, None

            # Traverse directory entries (12 bytes each)
            for _ in range(num_entries):
                entry = f.read(12)
                tag, tag_type, count, val_offset = struct.unpack(f"{endian}HHI I", entry)

                # Tag 256: ImageWidth, Tag 257: ImageLength
                if tag == 256:
                    w = val_offset
                elif tag == 257:
                    h = val_offset

                # Tag 306: DateTime -> Scrub with zeros
                elif tag == 306:
                    save_pos = f.tell()
                    f.seek(val_offset)
                    f.write(config.NDPI_DUMMY_DATETIME)
                    f.seek(save_pos)

            # Check if this IFD matches the macro image dimensions
            if macro_dims and (w, h) == macro_dims:
                is_macro_ifd = True

            # Offset pointing to the next IFD
            next_ifd_pointer_offset = f.tell()
            next_ifd_bytes = f.read(4)
            if len(next_ifd_bytes) < 4:
                break
            next_ifd_offset = struct.unpack(f"{endian}I", next_ifd_bytes)[0]

            if is_macro_ifd:
                # UNLINK: Point previous IFD's next-pointer to skip this macro IFD
                f.seek(prev_pointer_offset)
                f.write(struct.pack(f"{endian}I", next_ifd_offset))
                print(f"  [WSI] Unlinked Macro IFD ({w}x{h}) from TIFF chain.")
                break

            prev_pointer_offset = next_ifd_pointer_offset
            current_offset = next_ifd_offset

    # 3. Scrub textual references of S/N in Hamamatsu comment chunks
    if config.NDPI_SCRUB_BINARY_SN:
        _scrub_binary_strings(file_path)

    return True


def _scrub_binary_strings(file_path: Path):
    """Overwrites occurrences of serial number tags directly in the binary stream."""
    with open(file_path, "r+b") as f:
        chunk_size = min(64 * 1024 * 1024, os.path.getsize(file_path))
        data = f.read(chunk_size)

        idx = data.find(b"NDP.S/N=")
        if idx != -1:
            end_idx = data.find(b"\r\n", idx)
            if end_idx != -1:
                length = end_idx - (idx + 8)
                f.seek(idx + 8)
                f.write(b"0" * length)
                print("  [WSI] Overwrote scanner serial number in metadata block.")


def sanitize_info(info: dict) -> dict:
    """Removes local filesystem traces and sensitive tags from the JSON output."""
    info["filename"] = Path(info["filename"]).name

    phi_keys = [
        "tiff.DateTime",
        "hamamatsu.NDP.S/N",
        "hamamatsu.Created",
        "hamamatsu.Updated",
        "openslide.quickhash-1"
    ]
    for key in phi_keys:
        info["all_properties"].pop(key, None)

    return info


def analyze_ndpi(filename: Path) -> dict:
    """Extracts optical parameters, resolution, and sanitized slide properties."""
    slide = OpenSlide(str(filename))
    props = slide.properties

    info = {
        "filename": str(filename),
        "vendor": props.get("openslide.vendor"),
        "objective_power": props.get("openslide.objective-power"),
        "mpp_x_um": float(props.get("openslide.mpp-x", "nan")),
        "mpp_y_um": float(props.get("openslide.mpp-y", "nan")),
        "level_count": slide.level_count,
        "base_dimensions_px": list(slide.dimensions),
        "level_dimensions": [list(d) for d in slide.level_dimensions],
        "level_downsamples": list(slide.level_downsamples),
        "associated_images": list(slide.associated_images.keys()),
        "color_profile": str(slide.color_profile) if slide.color_profile else None,
        "all_properties": dict(props),
    }

    if info["mpp_x_um"] and info["mpp_y_um"]:
        w_um = info["base_dimensions_px"][0] * info["mpp_x_um"]
        h_um = info["base_dimensions_px"][1] * info["mpp_y_um"]
        info["physical_size_um"] = [w_um, h_um]
        info["physical_size_mm"] = [w_um / 1000, h_um / 1000]

    level_mpp = {}
    if info["mpp_x_um"]:
        for i, ds in enumerate(slide.level_downsamples):
            level_mpp[str(i)] = float(info["mpp_x_um"]) * ds
    info["level_mpp_um"] = level_mpp

    slide.close()

    # TIFF fallback for resolution tags (with tuple fix)
    try:
        with tifffile.TiffFile(str(filename)) as tif:
            tags = tif.pages[0].tags
            xres_raw = tags["XResolution"].value
            unit = tags["ResolutionUnit"].value

            if isinstance(xres_raw, tuple):
                xres = float(xres_raw[0]) / float(xres_raw[1])
            elif hasattr(xres_raw, "numerator") and hasattr(xres_raw, "denominator"):
                xres = float(xres_raw.numerator) / float(xres_raw.denominator)
            else:
                xres = float(xres_raw)

            if unit == 2:
                mpp_um = 25400 / xres
            elif unit == 3:
                mpp_um = 10000 / xres
            else:
                mpp_um = None

            info["tiff_xres"] = xres
            info["tiff_unit"] = unit
            info["tiff_mpp_um"] = mpp_um
    except Exception as e:
        info["tiff_metadata_error"] = str(e)

    return sanitize_info(info)

def anonymize_ndpi_file(src_path: str, target_out_path: str) -> str:
    """Copies NDPI file to target destination, unlinks Macro IFD, and exports clean metadata JSON."""
    src = Path(src_path).resolve()
    dst = Path(target_out_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    print(f"  [WSI] Copying {src.name} to {dst.name}...")
    shutil.copy2(src, dst)

    print(f"  [WSI] Unlinking Macro IFD and scrubbing tags on {dst.name}...")
    unlink_macro_image_and_scrub(dst)

    print(f"  [WSI] Writing clean metadata JSON...")
    meta = analyze_ndpi(dst)
    json_path = dst.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4)

    return str(dst)
def process_wsi_pipeline(source_path: str, output_dir: str) -> tuple:
    """Copies source NDPI, scrubs binary IFDs, and exports clean metadata JSON."""
    src = Path(source_path).resolve()
    dst = Path(output_dir) / f"anonymized_{src.name}"
    output_path = anonymize_ndpi_file(source_path, str(dst))
    return output_path, str(Path(output_path).with_suffix(".json"))


def get_ndpi_thumbnail_bgr(file_path: str, max_dim: int = 1024):
    """Extract a downsampled slide thumbnail in OpenCV BGR format."""
    try:
        with OpenSlide(file_path) as slide:
            if "macro" in slide.associated_images:
                image = slide.associated_images["macro"].convert("RGB")
            else:
                best_level = slide.level_count - 1
                image = slide.read_region(
                    (0, 0), best_level, slide.level_dimensions[best_level]
                ).convert("RGB")

            image.thumbnail((max_dim, max_dim))
            return np.array(image)[:, :, ::-1].copy()
    except Exception as e:
        print(f"  [WSI] Thumbnail preview generation failed: {e}")
        return None


def anonymize_ndpi_file(src_path: str, target_out_path: str) -> str:
    """Copy an NDPI file to its destination, scrub it, and export clean metadata."""
    src = Path(src_path).resolve()
    dst = Path(target_out_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    print(f"  [WSI] Copying {src.name} to {dst.name}...")
    shutil.copy2(src, dst)

    print(f"  [WSI] Unlinking Macro IFD and scrubbing tags on {dst.name}...")
    unlink_macro_image_and_scrub(dst, make_backup=False)

    print("  [WSI] Writing clean metadata JSON...")
    metadata = analyze_ndpi(dst)
    json_path = dst.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

    return str(dst)