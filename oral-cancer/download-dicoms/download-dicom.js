const axios = require("axios");
const fs = require("fs");
const path = require("path");
const unzipper = require("unzipper");

const OUTPUT_DIR = "<output directory path>";

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// Configure your dcm4chee-arc-light server details
const PACS_API = "https://{HOST}/dcm4chee-arc/aets/DCM4CHEE/rs";

const BEARER_TOKEN = "TOKEN";
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
      error.response?.data || error.message,
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
      },
    );

    if (response.data.length === 0) {
      console.log("No SR series found for study:", studyUID);
      return null;
    }

    return response.data;
  } catch (error) {
    console.error(
      "Error fetching series:",
      error.response?.data || error.message,
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
  modalityString,
) {
  const url = `${PACS_API}/studies/${studyUID}/series/${seriesUID}`;
  const seriesDir = path.join(outputDir, patientID, modalityString, studyDesc);

  if (!fs.existsSync(seriesDir)) {
    fs.mkdirSync(seriesDir, { recursive: true });
  }

  const tempZipPath = path.join(
    outputDir,
    `${patientID}_${modalityString}_${studyDesc}.zip`,
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
      error.message,
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
        modalityString,
      );
    }

    processedCount++;
  }

  console.log(
    `\n✅ Processing complete. Total studies processed: ${processedCount}`,
  );
}

main();
