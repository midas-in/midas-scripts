// Required Node.js modules
const fs = require("fs");
const path = require("path");
const bodySites = require("./bodySites.json");
const modalityList = require("./modalityList.json");

// Allowed image extensions for validation
const IMAGE_EXTENSIONS = [".jpeg", ".jpg", ".tif", ".png"];

const allowedBodySiteCodes = new Set(bodySites.map((site) => site.code));
const allowedModalityCodes = new Set(modalityList.map((m) => m.code));

// Object to track overall validation results
const results = {
  summary: {
    totalCases: 0,
    totalVisits: 0,
    validVisits: 0,
    invalidVisits: 0,
    totalErrors: 0,
  },
  details: {}, // Stores per-case and per-visit validation results
};

// Checks if a file has a valid image extension
function isValidImageFile(file, allowedExtensions) {
  return allowedExtensions.includes(path.extname(file).toLowerCase());
}

// Utility function to log an error and increment total error count
function logError(errors, message) {
  errors.push(message);
  results.summary.totalErrors++;
}

// Validates that a given leaf folder contains only valid image files
function validateLeafFolderContainsImages(
  folderPath,
  errors,
  allowedExtensions,
) {
  const files = fs.readdirSync(folderPath).filter((f) => !f.startsWith("."));
  for (const file of files) {
    const filePath = path.join(folderPath, file);

    if (
      !fs.statSync(filePath).isFile() ||
      !isValidImageFile(file, allowedExtensions)
    ) {
      logError(errors, `❌ Invalid file: ${file} in ${folderPath}`);
      return false;
    }
  }
  return true;
}

// Validates subfolders under a histopath folder, expecting magnification folders (e.g., 10x)
function validateGMSubfolder(basePath, label, errors) {
  let valid = true;

  const siteFolders = fs
    .readdirSync(basePath)
    .filter((name) => !name.startsWith("."));

  // Rule 4: If folder is empty → valid
  if (siteFolders.length === 0) return true;

  for (const site of siteFolders) {
    const sitePath = path.join(basePath, site);

    if (!fs.statSync(sitePath).isDirectory()) {
      logError(
        errors,
        `❌ Unexpected file "${site}" found inside "${label}" folder`,
      );
      valid = false;
      continue;
    }

    const siteSubFolders = fs
      .readdirSync(sitePath)
      .filter((name) => !name.startsWith("."));

    if (siteSubFolders.length === 0) continue;

    // Rule 5: Must be in allowed body site codes
    if (!allowedBodySiteCodes.has(site) && site !== "OTHERS") {
      logError(errors, `❌ Invalid body site folder "${site}" in ${label}`);
      valid = false;
      continue;
    }

    // Must be a directory
    if (!fs.statSync(sitePath).isDirectory()) {
      logError(errors, `❌ "${site}" in ${label} is not a directory`);
      valid = false;
      continue;
    }

    const magFolders = fs
      .readdirSync(sitePath)
      .filter((name) => !name.startsWith("."));

    // Rule 6: Can be empty → valid
    if (magFolders.length === 0) continue;

    for (const mag of magFolders) {
      const magPath = path.join(sitePath, mag);

      // Rule 7: Must be like 1x, 2x, 4x, 10x, etc.
      if (!/^[0-9]+(\.[0-9]+)?x$/.test(mag)) {
        logError(
          errors,
          `❌ Invalid magnification folder "${mag}" in ${label}/${site}`,
        );
        valid = false;
        continue;
      }

      if (!fs.statSync(magPath).isDirectory()) {
        logError(errors, `❌ "${mag}" in ${label}/${site} is not a directory`);
        valid = false;
        continue;
      }

      valid =
        validateLeafFolderContainsImages(magPath, errors, IMAGE_EXTENSIONS) &&
        valid;
    }
  }

  return valid;
}

function validateSpecialSubfolder(basePath, label, errors) {
  let valid = true;

  const magFolders = fs
    .readdirSync(basePath)
    .filter((name) => !name.startsWith("."));

  // Rule 4: If folder is empty → valid
  if (magFolders.length === 0) return true;

  for (const mag of magFolders) {
    const sitePath = path.join(basePath, mag);

    if (!fs.statSync(sitePath).isDirectory()) {
      logError(
        errors,
        `❌ Unexpected file "${mag}" found inside "${label}" folder`,
      );
      valid = false;
      continue;
    }

    const siteSubFolders = fs
      .readdirSync(sitePath)
      .filter((name) => !name.startsWith("."));

    if (siteSubFolders.length === 0) continue;

    // Must be a directory
    if (!fs.statSync(sitePath).isDirectory()) {
      logError(errors, `❌ "${mag}" in ${label} is not a directory`);
      valid = false;
      continue;
    }

    const magFolders = fs
      .readdirSync(sitePath)
      .filter((name) => !name.startsWith("."));

    // Rule 6: Can be empty → valid
    if (magFolders.length === 0) continue;

    for (const mag of magFolders) {
      const magPath = path.join(sitePath, mag);

      // Rule 7: Must be like 1x, 2x, 4x, 10x, etc.
      if (!/^[0-9]+x$/.test(mag)) {
        logError(
          errors,
          `❌ Invalid magnification folder "${mag}" in ${label}/${mag}`,
        );
        valid = false;
        continue;
      }

      if (!fs.statSync(magPath).isDirectory()) {
        logError(errors, `❌ "${mag}" in ${label}/${mag} is not a directory`);
        valid = false;
        continue;
      }

      valid =
        validateLeafFolderContainsImages(magPath, errors, IMAGE_EXTENSIONS) &&
        valid;
    }
  }

  return valid;
}

// Validates the GM folder
function validateGM(gmPath, errors) {
  let valid = true;

  const entries = fs
    .readdirSync(gmPath)
    .filter((name) => !name.startsWith("."));

  // ✅ Rule 1: GM is completely empty → valid
  if (entries.length === 0) {
    return true;
  }

  // ✅ Rule 2: GM must only contain CYTOLOGY or HISTOPATH (no extra folders/files)
  const allowedTopLevel = ["CYTOLOGY", "HISTOPATH", "IHC", "SPECIAL STAINS"];
  for (const entry of entries) {
    const fullPath = path.join(gmPath, entry);
    if (!allowedTopLevel.includes(entry)) {
      logError(
        errors,
        `❌ Unexpected entry "${entry}" in GM. Only HISTOPATH or CYTOLOGY are allowed.`,
      );
      valid = false;
    } else if (!fs.statSync(fullPath).isDirectory()) {
      logError(errors, `❌ "${entry}" in GM is not a directory`);
      valid = false;
    }
  }

  // ✅ Rule 3: If CYTOLOGY exists, validate it
  const cytologyPath = path.join(gmPath, "CYTOLOGY");
  if (fs.existsSync(cytologyPath) && fs.statSync(cytologyPath).isDirectory()) {
    valid = validateGMSubfolder(cytologyPath, "CYTOLOGY", errors) && valid;
  }

  // ✅ Rule 4: If HISTOPATH exists, validate it
  const histopathPath = path.join(gmPath, "HISTOPATH");
  if (
    fs.existsSync(histopathPath) &&
    fs.statSync(histopathPath).isDirectory()
  ) {
    valid = validateGMSubfolder(histopathPath, "HISTOPATH", errors) && valid;
  }

  return valid;
}

// Validates the SM folder (Soft Morphology)
function validateSM(smPath, errors) {
  const NDPI_ONLY = [".ndpi"];
  let valid = true;

  const entries = fs.readdirSync(smPath).filter((e) => !e.startsWith("."));

  // ✅ Rule 1 and 2: Only HISTOPATH and/or CYTOLOGY allowed
  const allowedFolders = ["HISTOPATH", "CYTOLOGY"];
  for (const entry of entries) {
    const entryPath = path.join(smPath, entry);
    const stat = fs.statSync(entryPath);

    if (!allowedFolders.includes(entry)) {
      logError(
        errors,
        `❌ Invalid folder "${entry}" found in SM. Only HISTOPATH and CYTOLOGY are allowed.`,
      );
      valid = false;
    } else if (!stat.isDirectory()) {
      logError(
        errors,
        `❌ Unexpected file "${entry}" found in SM. Only folders allowed.`,
      );
      valid = false;
    }
  }

  // Proceed only if folders exist
  const cytologyPath = path.join(smPath, "CYTOLOGY");
  const histopathPath = path.join(smPath, "HISTOPATH");

  if (!fs.existsSync(cytologyPath) && !fs.existsSync(histopathPath)) {
    // If SM exists but doesn't have CYTOLOGY or HISTOPATH — it's still valid as per rule 1
    return valid;
  }

  // ✅ Validate CYTOLOGY
  if (fs.existsSync(cytologyPath)) {
    const cytoEntries = fs
      .readdirSync(cytologyPath)
      .filter((f) => !f.startsWith("."));
    for (const sub of cytoEntries) {
      const subPath = path.join(cytologyPath, sub);
      const stat = fs.statSync(subPath);

      if (!stat.isDirectory()) {
        logError(
          errors,
          `❌ File "${sub}" found directly in CYTOLOGY — only folders allowed`,
        );
        valid = false;
        continue;
      }

      if (!allowedBodySiteCodes.has(sub)) {
        logError(errors, `❌ Invalid body site folder "${sub}" in CYTOLOGY`);
        valid = false;
        continue;
      }

      const isValid = validateLeafFolderContainsImages(
        subPath,
        errors,
        NDPI_ONLY,
      );
      valid = valid && isValid;
    }
  }

  // ✅ Validate HISTOPATH
  if (fs.existsSync(histopathPath)) {
    const histoEntries = fs
      .readdirSync(histopathPath)
      .filter((f) => !f.startsWith("."));
    for (const sub of histoEntries) {
      const subPath = path.join(histopathPath, sub);
      const stat = fs.statSync(subPath);

      if (!stat.isDirectory()) {
        logError(
          errors,
          `❌ File "${sub}" found directly in HISTOPATH — only folders allowed`,
        );
        valid = false;
        continue;
      }

      if (!allowedBodySiteCodes.has(sub)) {
        logError(errors, `❌ Invalid body site folder "${sub}" in HISTOPATH`);
        valid = false;
        continue;
      }

      const isValid = validateLeafFolderContainsImages(
        subPath,
        errors,
        NDPI_ONLY,
      );
      valid = valid && isValid;
    }
  }

  return valid;
}

// Validates the XC folder (Clinical)
function validateXC(xcPath, errors) {
  const entries = fs
    .readdirSync(xcPath)
    .filter((name) => !name.startsWith("."));

  // ✅ Rule 1: XC is completely empty (no visible files/folders) → treat as valid
  if (entries.length === 0) {
    return true;
  }

  const clinicalPath = path.join(xcPath, "CLINICAL");

  // ✅ Rule 2: CLINICAL must exist
  if (
    !fs.existsSync(clinicalPath) ||
    !fs.statSync(clinicalPath).isDirectory()
  ) {
    logError(errors, `❌ Missing CLINICAL folder in XC`);
    return false;
  }

  let valid = true;

  // ❌ Rule 3: XC must not contain any other files/folders (excluding hidden ones)
  for (const entry of entries) {
    if (entry !== "CLINICAL") {
      logError(errors, `❌ Unexpected file or folder "${entry}" found in XC`);
      valid = false;
    }
  }

  // ✅ Rule 4: Check if CLINICAL is empty
  const clinicalContents = fs
    .readdirSync(clinicalPath)
    .filter((name) => !name.startsWith("."));

  if (clinicalContents.length === 0) {
    // Just skip further validation silently
    return valid;
  }

  // ✅ Rule 5: Validate image files in CLINICAL
  valid =
    validateLeafFolderContainsImages(clinicalPath, errors, IMAGE_EXTENSIONS) &&
    valid;

  return valid;
}

// Validates the RG folder (Radiography)
function validateRG(rgPath, errors) {
  const entries = fs
    .readdirSync(rgPath)
    .filter((name) => !name.startsWith("."));

  // ✅ Rule 1: RG is completely empty (no visible files/folders) → treat as valid
  if (entries.length === 0) {
    return true;
  }

  const radioPath = path.join(rgPath, "RADIOGRAPH");

  // ✅ Rule 2: RADIOGRAPH must exist
  if (!fs.existsSync(radioPath) || !fs.statSync(radioPath).isDirectory()) {
    logError(errors, `❌ Missing RADIOGRAPH folder in RG`);
    return false;
  }

  let valid = true;

  // ❌ Rule 3: RG must not contain any other files/folders (excluding hidden ones)
  for (const entry of entries) {
    if (entry !== "RADIOGRAPH") {
      logError(errors, `❌ Unexpected file or folder "${entry}" found in RG`);
      valid = false;
    }
  }

  // ✅ Rule 4: Check if RADIOGRAPH is empty
  const radiographyContent = fs
    .readdirSync(radioPath)
    .filter((name) => !name.startsWith("."));

  if (radiographyContent.length === 0) {
    // Just skip further validation silently
    return valid;
  }

  // ✅ Rule 5: Validate image files in RADIOGRAPH
  valid =
    validateLeafFolderContainsImages(radioPath, errors, IMAGE_EXTENSIONS) &&
    valid;

  return valid;
}

// Validates the OT folder (Gross)
function validateOT(otPath, errors) {
  const entries = fs
    .readdirSync(otPath)
    .filter((name) => !name.startsWith("."));

  // ✅ Rule 1: OT is completely empty (no visible files/folders) → treat as valid
  if (entries.length === 0) {
    return true;
  }

  const grossPath = path.join(otPath, "GROSS");

  // ✅ Rule 2: GROSS must exist
  if (!fs.existsSync(grossPath) || !fs.statSync(grossPath).isDirectory()) {
    logError(errors, `❌ Missing GROSS folder in OT`);
    return false;
  }

  let valid = true;

  // ❌ Rule 3: OT must not contain any other files/folders (excluding hidden ones)
  for (const entry of entries) {
    if (entry !== "GROSS") {
      logError(errors, `❌ Unexpected file or folder "${entry}" found in OT`);
      valid = false;
    }
  }

  // ✅ Rule 4: Check if GROSS is empty
  const grossContent = fs
    .readdirSync(grossPath)
    .filter((name) => !name.startsWith("."));

  if (grossContent.length === 0) {
    // Just skip further validation silently
    return valid;
  }

  // ✅ Rule 5: Validate image files in GROSS
  valid =
    validateLeafFolderContainsImages(grossPath, errors, IMAGE_EXTENSIONS) &&
    valid;

  return valid;
}

// Validates the MOUTH folder, including its five subfolders
function validateMouth(mouthPath, errors) {
  const entries = fs
    .readdirSync(mouthPath)
    .filter((name) => !name.startsWith("."));

  let valid = true;

  for (const entry of entries) {
    const fullPath = path.join(mouthPath, entry);

    // Only process directories
    if (!fs.statSync(fullPath).isDirectory()) {
      logError(
        errors,
        `❌ Unexpected file "${entry}" found inside Body site folder`,
      );
      valid = false;
      continue;
    }

    // ✅ Rule 1: Must be a valid modality code from the JSON
    if (!allowedModalityCodes.has(entry)) {
      logError(errors, `❌ Invalid modality folder "${entry}" inside MOUTH`);
      valid = false;
      continue;
    }

    // ✅ Rule 2: Call corresponding validator
    switch (entry) {
      case "GM":
        valid = validateGM(fullPath, errors) && valid;
        break;
      case "SM":
        valid = validateSM(fullPath, errors) && valid;
        break;
      case "XC":
        valid = validateXC(fullPath, errors) && valid;
        break;
      case "RG":
        valid = validateRG(fullPath, errors) && valid;
        break;
      case "OT":
        valid = validateOT(fullPath, errors) && valid;
        break;
      default:
        logError(
          errors,
          `⚠️ No validator function defined for modality "${entry}"`,
        );
        valid = false;
        break;
    }
  }

  return valid;
}

// Validates a VISIT folder
function validateVisit(visitPath, caseName, visitName) {
  const errors = [];
  let valid = true;

  const folderEntries = fs
    .readdirSync(visitPath)
    .filter((name) => !name.startsWith("."));

  // ✅ Iterate each folder under VISIT_xx
  for (const folder of folderEntries) {
    const fullPath = path.join(visitPath, folder);
    const isDir = fs.statSync(fullPath).isDirectory();

    if (!isDir) {
      logError(
        errors,
        `❌ Unexpected file "${folder}" found inside visit folder.`,
      );
      valid = false;
      continue;
    }

    // ✅ Rule 1: Check if folder name is a known body site code
    if (!allowedBodySiteCodes.has(folder)) {
      logError(
        errors,
        `❌ Unknown body site folder "${folder}" in visit "${visitName}".`,
      );
      valid = false;
      continue;
    }

    // ⚠️ Rule 2: If folder is valid but empty — skip validation
    const subEntries = fs
      .readdirSync(fullPath)
      .filter((name) => !name.startsWith("."));
    if (subEntries.length === 0) {
      console.warn(
        `⚠️ Body site folder "${folder}" in visit "${visitName}" for "${caseName}" is empty. Skipping.`,
      );
      continue;
    }

    // ✅ Otherwise, pass to MOUTH-style validation logic
    valid = validateMouth(fullPath, errors) && valid;
  }

  // Update visit summary
  results.summary.totalVisits++;
  valid ? results.summary.validVisits++ : results.summary.invalidVisits++;

  // Save results
  if (!results.details[caseName]) results.details[caseName] = {};
  results.details[caseName][visitName] = { valid, errors };

  return valid;
}

// Validates a case folder containing one or more visits
function validateCase(casePath, caseName) {
  results.summary.totalCases++;

  const items = fs
    .readdirSync(casePath)
    .filter((name) => !name.startsWith("."));

  if (items.length === 0) {
    console.warn(`⚠️ Case folder "${caseName}" is empty. Skipping.`);
    return;
  }

  for (const item of items) {
    const itemPath = path.join(casePath, item);
    const isDir = fs.statSync(itemPath).isDirectory();

    // ❌ Rule 1: No files allowed
    if (!isDir) {
      throw new Error(
        `❌ File "${item}" found inside case "${caseName}". Only folders are allowed.`,
      );
    }

    // ❌ Rule 2: Folder must start with VISIT_
    if (!item.startsWith("VISIT_")) {
      throw new Error(
        `❌ Invalid folder "${item}" inside case "${caseName}". Only folders starting with 'VISIT_' are allowed.`,
      );
    }

    // ✅ Rule 3: Must follow VISIT_DD-MM-YYYY format
    const visitDate = item.slice(6); // Strip 'VISIT_'
    const dateRegex = /^(0[1-9]|[12][0-9]|3[01])-(0[1-9]|1[012])-\d{4}$/;
    if (!dateRegex.test(visitDate)) {
      throw new Error(
        `❌ Visit folder "${item}" inside case "${caseName}" has invalid date format. Expected 'VISIT_DD-MM-YYYY'.`,
      );
    }

    // ❌ Rule 4: VISIT_ folder must not be empty
    const visitContents = fs
      .readdirSync(itemPath)
      .filter((name) => !name.startsWith("."));
    if (visitContents.length === 0) {
      console.warn(
        `⚠️ Visit folder "${item}" inside case "${caseName}" is empty. Skipping further validation.`,
      );
      continue;
    }

    // ✅ Passed all checks → validate visit
    validateVisit(itemPath, caseName, item);
  }
}

// Validates the entire root folder (e.g., new-root/)
function validateRoot(rootPath) {
  const caseEntries = fs
    .readdirSync(rootPath)
    .filter((name) => !name.startsWith(".")); // Ignore hidden files/folders

  if (caseEntries.length === 0) {
    console.warn("⚠️ No case folders found in the root directory.");
    return;
  }

  for (const entry of caseEntries) {
    const entryPath = path.join(rootPath, entry);

    // If the entry is NOT a directory, it's an invalid item
    if (!fs.statSync(entryPath).isDirectory()) {
      throw new Error(
        `❌ Invalid file "${entry}" found in root directory. Only folders with caseId are allowed like 'case_01', 'case_02'.`,
      );
    }

    // Check if the case folder is empty (ignoring hidden files)
    const innerItems = fs
      .readdirSync(entryPath)
      .filter((name) => !name.startsWith("."));

    if (innerItems.length === 0) {
      console.warn(`⚠️ Skipping empty case folder: ${entry}`);
      continue;
    }

    // Now safe to validate this case folder
    validateCase(entryPath, entry);
  }
}

// 🔁 Replace this with your actual extracted path
const ROOT_DIR = path.resolve("root directory path");

// Run the validation
validateRoot(ROOT_DIR);

// Save output as JSON for machine-readable result
fs.writeFileSync("validation-report.json", JSON.stringify(results, null, 2));

// Generate and save output as HTML for human-readable report
const html = `
<!DOCTYPE html>
<html>
<head><title>Validation Report</title></head>
<body style="font-family:Arial,sans-serif;">
<h1>📊 Validation Report</h1>
<p><strong>Total Cases:</strong> ${results.summary.totalCases}</p>
<p><strong>Total Visits:</strong> ${results.summary.totalVisits}</p>
<p><strong>Valid Visits:</strong> ${results.summary.validVisits} ✅</p>
<p><strong>Invalid Visits:</strong> ${results.summary.invalidVisits} ❌</p>
<p><strong>Total Errors:</strong> ${results.summary.totalErrors}</p>
<hr/>
${Object.entries(results.details)
  .map(
    ([caseName, visits]) =>
      `<h2>🗂 ${caseName}</h2>` +
      Object.entries(visits)
        .map(
          ([visit, { valid, errors }]) =>
            `<div style="margin-left:20px;">
      <p><strong>${visit}:</strong> ${valid ? "✅ Valid" : "❌ Invalid"}</p>
      ${
        errors.length > 0
          ? `<ul>${errors.map((e) => `<li>${e}</li>`).join("")}</ul>`
          : ""
      }
    </div>`,
        )
        .join(""),
  )
  .join("")}
</body></html>
`;
fs.writeFileSync("validation-report.html", html);

// Done
console.log(
  "✅ Validation complete. Reports generated:\n- validation-report.json\n- validation-report.html",
);
