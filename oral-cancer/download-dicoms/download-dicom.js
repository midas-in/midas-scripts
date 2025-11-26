const axios = require("axios");
const fs = require("fs");
const path = require("path");
const unzipper = require("unzipper");

const OUTPUT_DIR = "/Users/triveous/Dev/Scripts/Download-dicoms/files";

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// Configure your dcm4chee-arc-light server details
const PACS_API = "https://hub.midashealth.in/dcm4chee-arc/aets/DCM4CHEE/rs";

const BEARER_TOKEN =
  "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJEQkV2c1czN2tvTTh5aFhjRTJnX3ZnWUlaNzA3ZDlMMEJHRGRMSmlrVEtJIn0.eyJleHAiOjE3NjE1OTM2NDIsImlhdCI6MTc2MTU1NzY0MiwianRpIjoiNzk1NzJmZjctNGE0Yy00ZmVhLTk2MjktZjRkYzQ5MmE1NDY2IiwiaXNzIjoiaHR0cHM6Ly9odWIubWlkYXNoZWFsdGguaW4vYXV0aC9yZWFsbXMvbWlkYXMiLCJhdWQiOlsicmVhbG0tbWFuYWdlbWVudCIsImFjY291bnQiXSwic3ViIjoiM2UyODNhOTctZmM5OS00Nzk3LWI4MWYtYTZkYTAzZmY4ODhmIiwidHlwIjoiQmVhcmVyIiwiYXpwIjoiYXV0aC1hcGlzIiwic2Vzc2lvbl9zdGF0ZSI6IjhhMTkzYzQ4LTlhMzYtNDU1YS1hYzY2LWM3Nzc4N2VjM2FiYiIsImFjciI6IjEiLCJhbGxvd2VkLW9yaWdpbnMiOlsiLyoiXSwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbInB1YmxpY2F0aW9uc19hY2Nlc3NfcmVhZCIsInVzZXJfcm9sZV9hY2Nlc3NfY3JlYXRlIiwicHVibGljYXRpb25zX2FjY2Vzc19jcmVhdGUiLCJhc3NpZ25fYWNjZXNzX3JlYWQiLCJ1c2VyX21hbmFnZW1lbnRfYWNjZXNzX3VwZGF0ZSIsInBhY3NfcmVhZCIsInVzZXJfbWFuYWdlbWVudF9hY2Nlc3NfcmVhZCIsImRlZmF1bHQtcm9sZXMtbWlkYXMiLCJhcGlfa2V5X2FjY2Vzc191cGRhdGUiLCJvZmZsaW5lX2FjY2VzcyIsInB1YmxpY2F0aW9uc19hY2Nlc3NfdXBkYXRlIiwiYXNzaWduX2FjY2Vzc191cGRhdGUiLCJ1bWFfYXV0aG9yaXphdGlvbiIsInJlcXVlc3RfYWNjZXNzX2NyZWF0ZSIsInJlcXVlc3RfYWNjZXNzX3VwZGF0ZSIsImd1aWRlbGluZXNfYWNjZXNzX3JlYWQiLCJwdWJsaXNoX2FjY2Vzc19yZWFkIiwiYXBpX2tleV9hY2Nlc3NfY3JlYXRlIiwibG9nc19hY2Nlc3NfcmVhZCIsInJlcXVlc3RfYWNjZXNzX3JlYWQiLCJ1c2VyX3JvbGVfYWNjZXNzX3JlYWQiLCJwYWNzX3dyaXRlIiwidXNlcl9yb2xlX2FjY2Vzc191cGRhdGUiLCJwdWJsaXNoX2FjY2Vzc191cGRhdGUiLCJkYXNoYm9hcmRfYWNjZXNzX3JlYWQiLCJhcGlfa2V5X2FjY2Vzc19yZWFkIiwidXNlcl9tYW5hZ2VtZW50X2FjY2Vzc19jcmVhdGUiLCJyb2xlLWFkbWluIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsicmVhbG0tbWFuYWdlbWVudCI6eyJyb2xlcyI6WyJ2aWV3LXJlYWxtIiwidmlldy1pZGVudGl0eS1wcm92aWRlcnMiLCJtYW5hZ2UtaWRlbnRpdHktcHJvdmlkZXJzIiwiaW1wZXJzb25hdGlvbiIsInJlYWxtLWFkbWluIiwiY3JlYXRlLWNsaWVudCIsIm1hbmFnZS11c2VycyIsInF1ZXJ5LXJlYWxtcyIsInZpZXctYXV0aG9yaXphdGlvbiIsInF1ZXJ5LWNsaWVudHMiLCJxdWVyeS11c2VycyIsIm1hbmFnZS1ldmVudHMiLCJtYW5hZ2UtcmVhbG0iLCJ2aWV3LWV2ZW50cyIsInZpZXctdXNlcnMiLCJ2aWV3LWNsaWVudHMiLCJtYW5hZ2UtYXV0aG9yaXphdGlvbiIsIm1hbmFnZS1jbGllbnRzIiwicXVlcnktZ3JvdXBzIl19LCJhY2NvdW50Ijp7InJvbGVzIjpbIm1hbmFnZS1hY2NvdW50IiwibWFuYWdlLWFjY291bnQtbGlua3MiLCJ2aWV3LXByb2ZpbGUiXX19LCJzY29wZSI6InByb2ZpbGUgZW1haWwiLCJzaWQiOiI4YTE5M2M0OC05YTM2LTQ1NWEtYWM2Ni1jNzc3ODdlYzNhYmIiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwibmFtZSI6Imh1YiBhZG1pbiIsInByZWZlcnJlZF91c2VybmFtZSI6ImFkbWluIiwiZ2l2ZW5fbmFtZSI6Imh1YiIsImZhbWlseV9uYW1lIjoiYWRtaW4iLCJlbWFpbCI6InN1cmFqZG9uZ3JlQHRyaXZlb3VzLmNvbSJ9.WF8y6Kfy-SpiXH4BI-d60gTuNutFjDU-TMxi8oW_Ve5EqjLZQAX_Mqa5shqm_zu2Dy-q7ogK4NWL3BPqWaDJkn75AzF4e8qK6kKTF_9ro9WDaLz_K057cuHkLE8yXeEc3ASodPgdovw2wdHZ1x2Q200tX80qzTc7e4-D2Nxg4wq3nvnY9e5OGhC1M9vL3aPrcfrbP5x6d6H0pN8aRMfJqjWaAJ-8YfNU4b9PHrI18zHOJGtrsYnLT8TZWQ0CSW7gz9I95vhPotFtTAKKxwb2vGhlVWzDgwM1_OfwX8H7l0HgChIqiwzV84liuFxttFKjSdUNe0uQPRQ3MVyE7wIb2Q";
// Create an Axios instance with default headers (optional but recommended)
const apiClient = axios.create({
  headers: {
    Authorization: `Bearer ${BEARER_TOKEN}`,
    Accept: "application/json",
  },
  // Add timeout to prevent hanging
  // timeout: 30000
});

async function fetchAllStudies() {
  try {
    const response = await apiClient.get(`${PACS_API}/studies`, {
      params: {
        ModalitiesInStudy: "SR",
        includefield: "0020000D,00100020,00081030",
        fuzzymatching: true,
      },
    });
    return response.data;
  } catch (error) {
    console.error(
      "Error fetching studies:",
      error.response?.data || error.message
    );
    return [];
  }
}

async function getLatestSeries(studyUID) {
  try {
    const response = await apiClient.get(
      `${PACS_API}/studies/${studyUID}/series`,
      {
        params: {
          ModalitiesInStudy: "SR",
          limit: 100,
          orderby: "SeriesNumber",
          includefield: "all",
        },
      }
    );

    if (response.data.length === 0) {
      console.log("No SR series found for study:", studyUID);
      return null;
    }

    return response.data;
  } catch (error) {
    console.error(
      "Error fetching series:",
      error.response?.data || error.message
    );
    return null;
  }
}

async function downloadSeries(
  studyUID,
  seriesUID,
  outputDir,
  patientID,
  studyDesc,
  modalityString
) {
  const url = `${PACS_API}/studies/${studyUID}/series/${seriesUID}`;
  const seriesDir = path.join(outputDir, patientID, modalityString, studyDesc);

  if (!fs.existsSync(seriesDir)) {
    fs.mkdirSync(seriesDir, { recursive: true });
  }

  const tempZipPath = path.join(
    outputDir,
    `${patientID}_${modalityString}_${studyDesc}.zip`
  );

  try {
    const response = await apiClient.get(url, {
      responseType: "stream",
      headers: {
        Accept: "application/zip",
      },
    });

    const writer = fs.createWriteStream(tempZipPath);
    response.data.pipe(writer);

    await new Promise((resolve, reject) => {
      writer.on("finish", resolve);
      writer.on("error", reject);
    });

    // ✅ Unzip the downloaded file into the desired folder
    // ✅ Delete the temp zip after extraction
    try {
      await fs
        .createReadStream(tempZipPath)
        .pipe(unzipper.Extract({ path: seriesDir }))
        .promise();
    } finally {
      if (fs.existsSync(tempZipPath)) fs.unlinkSync(tempZipPath);
    }

    console.log(`Downloaded and extracted series ${seriesUID} to ${seriesDir}`);
    return seriesDir;
  } catch (error) {
    console.error(
      `Error downloading or extracting series ${seriesUID}:`,
      error.message
    );
  }
}

async function main() {
  console.log("Fetching all studies with SR modality...");
  const studies = await fetchAllStudies();

  console.log(`Total studies fetched from PACS: ${studies.length}`);

  // 🧾 Read allowed study UIDs from text file
  const allowedUIDs = fs
    .readFileSync("study_uids.txt", "utf8")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  console.log(`Loaded ${allowedUIDs.length} study UIDs from text file.`);

  // 🔍 Filter fetched studies to include only those in the list
  const filteredStudies = studies.filter((study) => {
    const studyUID = study["0020000D"]?.Value?.[0];
    return allowedUIDs.includes(studyUID);
  });

  console.log(`Processing ${filteredStudies.length} matching studies...`);

  let processedCount = 0;

  for (const study of filteredStudies) {
    const studyUID = study["0020000D"].Value[0];
    const patientID = study["00100020"]?.Value?.[0] || "Unknown";
    const studyDesc = study["00081030"]?.Value?.[0] || "N/A";
    const modalityString = (study["00080061"]?.Value || [])
      .filter((m) => m !== "SR")
      .join("\\");

    console.log(`Modality String: ${modalityString}`);
    console.log(`\n🔹 Processing study: ${studyUID} (${studyDesc})`);

    const seriesList = await getLatestSeries(studyUID);
    if (!seriesList) {
      console.warn(`⚠️ No series found for study: ${studyUID}`);
      continue;
    }

    // You can pick first + last series or all of them
    const selectedSeries = [seriesList[0], seriesList[seriesList.length - 1]];

    for (const series of selectedSeries) {
      const seriesUID = series["0020000E"]?.Value?.[0];
      if (!seriesUID) continue;

      await downloadSeries(
        studyUID,
        seriesUID,
        OUTPUT_DIR,
        patientID,
        studyDesc,
        modalityString
      );
    }

    processedCount++;
  }

  console.log(
    `\n✅ Processing complete. Total studies processed: ${processedCount}`
  );
}

main();
