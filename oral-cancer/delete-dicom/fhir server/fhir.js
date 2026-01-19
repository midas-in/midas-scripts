const axios = require("axios");
const fs = require("fs");
const path = require("path");

// Configuration
const fhirBaseUrl = "https://{HOST}/fhir";

// Log files
const logDir = path.join(__dirname, "fhir_logs");
const summaryLogFile = path.join(logDir, "summary.log");
const errorLogFile = path.join(logDir, "errors.log");

// Ensure log directory exists
if (!fs.existsSync(logDir)) {
  fs.mkdirSync(logDir);
}

// Helper to write to log file
function appendLog(file, message) {
  fs.appendFileSync(file, `${new Date().toISOString()} - ${message}\n`);
}

// Function to delete ImagingStudy by ID
async function deleteImagingStudy(imagingStudyId) {
  try {
    const url = `${fhirBaseUrl}/ImagingStudy/${imagingStudyId}`;

    const response = await axios.delete(url);

    appendLog(
      summaryLogFile,
      `Successfully deleted ImagingStudy ${imagingStudyId}.`,
    );
    console.log(`Deleted ImagingStudy ${imagingStudyId}`);
    return true;
  } catch (error) {
    appendLog(
      errorLogFile,
      `Failed to delete ImagingStudy ${imagingStudyId}: ${
        error.response?.status || ""
      } - ${error.message}`,
    );
    console.error(
      `Failed to delete ImagingStudy ${imagingStudyId}: ${error.message}`,
    );
    return false;
  }
}

// Main workflow
async function main() {
  appendLog(summaryLogFile, "=== ImagingStudy Delete Script Started ===");

  try {
    // List of ImagingStudy IDs to delete
    const imagingStudyIds = [
      "1.2.826.0.1.3680043.8.498.16974876395105676814040601981360817502",
    ];

    let deletedCount = 0;
    let failedCount = 0;

    for (const imagingStudyId of imagingStudyIds) {
      const success = await deleteImagingStudy(imagingStudyId);
      if (success) {
        deletedCount++;
      } else {
        failedCount++;
      }
    }

    appendLog(
      summaryLogFile,
      `Total ImagingStudies to delete: ${imagingStudyIds.length}`,
    );
    appendLog(summaryLogFile, `Successfully deleted: ${deletedCount}`);
    appendLog(summaryLogFile, `Failed deletions: ${failedCount}`);
    appendLog(summaryLogFile, "=== ImagingStudy Delete Script Finished ===");
  } catch (error) {
    appendLog(errorLogFile, `Script failed: ${error.message}`);
    appendLog(summaryLogFile, "=== Script Terminated with Errors ===");
  }
}

main();
