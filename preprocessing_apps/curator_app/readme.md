MIDAS Image Curation System 

Clinical Image Archival Application for Hospital Curators

A desktop GUI tool designed to organise, rename, archive, and document medical images into the standardized MIDAS folder structure with automatic metadata logging.

Built using PyQt6 for hospital-grade workflow efficiency.


---

Features

Image Curation

Thumbnail-based image preview

Multi-image selection

Select All / Deselect All

Visual "Organised" badge after processing

USB / external drive support


Automatic Folder Structure

Creates standardized MIDAS hierarchy:

MIDAS_CODE/
 └── VISIT_DATE/
     └── MOUTH/
         ├── XC/
         ├── RG/
         ├── GM/
         ├── SM/
         └── OT/

Supports:

Clinical Photography (XC)

Radiograph (RG)

General Microscopy (GM)

Slide Microscopy (SM)

Other (OT)



---

Automatic File Naming

Files are renamed using MIDAS standard:

MIDASCODE_VISIT_DATE_CATEGORY_BODYSITE_MAG_001.jpg

Example:

MIDAS001_VISIT_26-06-2025_GM_TONG_40x_001.jpg


---

Metadata CSV Generation

One CSV per MIDAS case:

MIDAS_CODE/
 └── MIDAS_CODE_metadata.csv

Features:

Auto row merge per visit

Automatic count aggregation

Multiple organise passes supported

No duplicate rows


CSV Columns:

UHID
MIDAS_CODE
VisitDate
BodySite
XC
RG
Gross
Special_Stains
IHC
Cytology
Genomic
Histopath_4x
Histopath_10x
Histopath_20x
Histopath_40x
Histopath_100x
WSI
Curator


---

Session Logging

Each session creates:

root/logs/curation_log_YYYYMMDD_HHMMSS.txt

Log contains:

Files organised

Destination folders

MIDAS code

Curator name

Category path

CSV save events

Session start/end



---

UI Workflow

Step 1 — Root Storage

Select main MIDAS storage directory

Step 2 — Patient Information

UHID

MIDAS Code

Curator

Visit Date


Step 3 — Category

XC — Clinical Photography

RG — Radiograph

GM — General Microscopy

SM — Slide Microscopy

OT — Other


Step 4 — Subcategory (conditional)

Examples:

HISTOPATH

CYTOLOGY

IHC

SPECIAL_STAINS

GROSS

GENOMIC


Step 5 — Body Site (conditional)

Supports:

Single site

Multi site selection


Step 6 — Magnification (conditional)

4x

10x

20x

40x

100x



---

Save Controls

Three independent actions:

Organise Images

Copies images

Renames files

Creates folder structure

Prepares metadata


Save CSV

Writes metadata to MIDAS CSV

Merges duplicate sessions

Aggregates counts


Save Log

Saves session audit log

Continuous logging enabled



---

Requirements

Python 3.9+

Install dependency:

pip install PyQt6


---

Usage

Run:

python midas_curation.py


---

Supported Image Formats

.jpg
.jpeg
.png
.bmp
.tiff
.tif


---

Safety Features

Prevents overwrite using auto counters

Warns before closing with unsaved data

USB removal detection

Root folder validation

Global exception handler

Progress bar during copy

Session recovery prompts



---

Folder Builder Logic

Examples:

Clinical Photo

MIDAS/VISIT/MOUTH/XC/CLINICAL/

Radiograph

MIDAS/VISIT/MOUTH/RG/RADIOGRAPH/

Histopathology

MIDAS/VISIT/MOUTH/GM/HISTOPATH/TONG/40x/

Cytology

MIDAS/VISIT/MOUTH/GM/CYTOLOGY/10x/

Gross

MIDAS/VISIT/MOUTH/OT/GROSS/


---

Multi Body Site Support

If multiple sites selected:

Images copied to:

TONG/
BUCCA/
PALAT/

Each with independent counters.


---

Example Workflow

1. Insert USB with images


2. Select root storage


3. Enter MIDAS code


4. Select category


5. Choose body site


6. Select images


7. Click Organise Images


8. Click Save CSV


9. Click Save Log



Done.


---

Version

MIDAS Curation System
Version: v2.0


---

Designed For

Hospital curators

Pathology labs

Oral oncology datasets

Clinical image archiving

Research data curation

MIDAS dataset standardization



---

License

Internal Clinical Research Tool
AIIMS / MIDAS Workflow System
