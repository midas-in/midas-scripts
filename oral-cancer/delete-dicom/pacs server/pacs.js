const fs = require("fs");
const { execSync } = require("child_process");

// ---- CONFIGURATION ----
const PACS_BASE_URL = "https://{HOST}/dcm4chee-arc/aets/DCM4CHEE/rs/studies";
const REJECT_CODE = "113039%5EDCM"; // reason for rejection
const TOKEN = "TOKEN";
const INPUT_FILE = "study_uids.txt"; // file containing StudyInstanceUIDs (one per line)
const SUCCESS_LOG = "pacs_deleted.log";
const FAILED_LOG = "pacs_failed.log";

// ---- CHECK INPUT ----
if (!fs.existsSync(INPUT_FILE)) {
  console.error(`❌ File not found: ${INPUT_FILE}`);
  process.exit(1);
}

// ---- READ UIDs ----
const uids = fs
  .readFileSync(INPUT_FILE, "utf8")
  .split(/\r?\n/)
  .map((l) => l.trim())
  .filter(Boolean);

console.log(`📚 Found ${uids.length} studies to delete.`);

// ---- CLEAN OLD LOG FILES ----
fs.writeFileSync(SUCCESS_LOG, "", "utf8");
fs.writeFileSync(FAILED_LOG, "", "utf8");

// ---- DELETE EACH STUDY ----
uids.forEach((uid, index) => {
  console.log(`\n🧾 [${index + 1}/${uids.length}] Deleting Study: ${uid}`);
  try {
    const cmd = `curl -s -o /dev/null -w "%{http_code}" \
      -X POST "${PACS_BASE_URL}/${uid}/reject/${REJECT_CODE}" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      --data '{}'`;

    const response = execSync(cmd).toString().trim();

    if (response === "200" || response === "204") {
      console.log(`✅ Successfully deleted ${uid}`);
      fs.appendFileSync(SUCCESS_LOG, `${uid}\n`);
    } else {
      console.log(`⚠️ Failed to delete ${uid} (HTTP ${response})`);
      fs.appendFileSync(FAILED_LOG, `${uid} - HTTP ${response}\n`);
    }
  } catch (err) {
    console.error(`❌ Error deleting ${uid}:`, err.message);
    fs.appendFileSync(FAILED_LOG, `${uid} - ERROR: ${err.message}\n`);
  }
});

console.log("\n🏁 Completed all deletions.");
console.log(`📘 Success log: ${SUCCESS_LOG}`);
console.log(`📕 Failure log: ${FAILED_LOG}`);
