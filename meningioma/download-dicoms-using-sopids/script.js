const axios = require("axios");
const fs = require("fs");
const path = require("path");
const unzipper = require("unzipper");

const OUTPUT_DIR =
  "folder-path";

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// Configure your dcm4chee-arc-light server details
const PACS_API =
  "pacs-url";

const BEARER_TOKEN =
  "auth-token";
// Create an Axios instance with default headers (optional but recommended)
const apiClient = axios.create({
  headers: {
    Authorization: `Bearer ${BEARER_TOKEN}`,
    Accept: "application/json",
  },
  // Add timeout to prevent hanging
  // timeout: 30000
});

function loadAllowedStudyUIDs(filePath) {
  return new Set(
    fs
      .readFileSync(filePath, "utf8")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean),
  );
}

async function fetchStudyByUID(studyUID) {
  try {
    const res = await apiClient.get(`${PACS_API}/studies`, {
      params: {
        StudyInstanceUID: studyUID,
        includefield: "0020000D,00100020,00081030,00080061",
      },
    });
    return res.data?.[0] || null;
  } catch (err) {
    console.error(`Failed to fetch study ${studyUID}`, err.message);
    return null;
  }
}

async function getLatestSeries(studyUID) {
  try {
    const response = await apiClient.get(
      `${PACS_API}/studies/${studyUID}/series`,
      {
        params: {
          limit: 1000,
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
  // 🧾 Read allowed study UIDs from text file
  const allowedStudyUIDs = loadAllowedStudyUIDs("study_uids.txt");
  console.log(`Loaded ${allowedStudyUIDs.size} study UIDs from file`);

  let processedCount = 0;

  for (const studyUID of allowedStudyUIDs) {
    const study = await fetchStudyByUID(studyUID);
    if (!study) {
      console.warn(`⚠️ Study not found: ${studyUID}`);
      continue;
    }

    // const studyUID = study["0020000D"].Value[0];
    const patientID = study["00100020"]?.Value?.[0] || "Unknown";
    const studyDesc = study["00081030"]?.Value?.[0] || "N/A";
    const modalityString = (study["00080061"]?.Value || [])
      .filter((m) => m !== "SEG")
      .join("\\");

    console.log(`Modality String: ${modalityString}`);
    console.log(`\n🔹 Processing study: ${studyUID} (${studyDesc})`);

    const seriesList = await getLatestSeries(studyUID);
    if (!seriesList) {
      console.warn(`⚠️ No series found for study: ${studyUID}`);
      continue;
    }

    // You can pick first + last series or all of them
    const selectedSeries = seriesList;

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
