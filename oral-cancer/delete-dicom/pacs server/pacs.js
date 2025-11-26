const fs = require("fs");
const { execSync } = require("child_process");

// ---- CONFIGURATION ----
const PACS_BASE_URL =
  "https://pgichn.meningioma.midaspacs.in/dcm4chee-arc/aets/DCM4CHEE/rs/studies";
const REJECT_CODE = "113039%5EDCM"; // reason for rejection
const TOKEN =
  "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJ1RlNMbGh1TVZ3SlRLNF9GY1lYQzBJbUFLMHEwTWtvcGpyaEJITnIwYlpVIn0.eyJleHAiOjE3NjQyMjE3NzYsImlhdCI6MTc2NDEzNTM3NiwianRpIjoiZGI1ODc4ZTgtZWFkYi00Y2NkLWFiZTktODc4N2M2OWI1OTA5IiwiaXNzIjoiaHR0cHM6Ly9wZ2ljaG4ubWVuaW5naW9tYS5taWRhc3BhY3MuaW4vYXV0aC9yZWFsbXMvbWlkYXMiLCJhdWQiOlsicmVhbG0tbWFuYWdlbWVudCIsImFjY291bnQiXSwic3ViIjoiNzJmNTJlMzktZmMzYy00YzBlLWJkZTEtZDg3OTFiNTQyMDMwIiwidHlwIjoiQmVhcmVyIiwiYXpwIjoiYXV0aC1hcGlzIiwic2lkIjoiNzlkYWYyM2UtMjZjMS00MzZkLTkwZjUtZmEzYWY4MDhmMmYxIiwiYWNyIjoiMSIsImFsbG93ZWQtb3JpZ2lucyI6WyIvKiJdLCJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsicHVibGljYXRpb25zX2FjY2Vzc19yZWFkIiwidXNlcl9yb2xlX2FjY2Vzc19jcmVhdGUiLCJwdWJsaWNhdGlvbnNfYWNjZXNzX2NyZWF0ZSIsImFzc2lnbl9hY2Nlc3NfcmVhZCIsInVzZXJfbWFuYWdlbWVudF9hY2Nlc3NfdXBkYXRlIiwicGFjc19yZWFkIiwidXNlcl9tYW5hZ2VtZW50X2FjY2Vzc19yZWFkIiwiZGVmYXVsdC1yb2xlcy1taWRhcyIsImFwaV9rZXlfYWNjZXNzX3VwZGF0ZSIsIm9mZmxpbmVfYWNjZXNzIiwicHVibGljYXRpb25zX2FjY2Vzc191cGRhdGUiLCJhc3NpZ25fYWNjZXNzX3VwZGF0ZSIsInVtYV9hdXRob3JpemF0aW9uIiwicmVxdWVzdF9hY2Nlc3NfY3JlYXRlIiwicmVxdWVzdF9hY2Nlc3NfdXBkYXRlIiwiZ3VpZGVsaW5lc19hY2Nlc3NfcmVhZCIsInB1Ymxpc2hfYWNjZXNzX3JlYWQiLCJhcGlfa2V5X2FjY2Vzc19jcmVhdGUiLCJsb2dzX2FjY2Vzc19yZWFkIiwicmVxdWVzdF9hY2Nlc3NfcmVhZCIsInVzZXJfcm9sZV9hY2Nlc3NfcmVhZCIsInBhY3Nfd3JpdGUiLCJ1c2VyX3JvbGVfYWNjZXNzX3VwZGF0ZSIsInB1Ymxpc2hfYWNjZXNzX3VwZGF0ZSIsImRhc2hib2FyZF9hY2Nlc3NfcmVhZCIsImFwaV9rZXlfYWNjZXNzX3JlYWQiLCJ1c2VyX21hbmFnZW1lbnRfYWNjZXNzX2NyZWF0ZSIsInJvbGUtYWRtaW4iXX0sInJlc291cmNlX2FjY2VzcyI6eyJyZWFsbS1tYW5hZ2VtZW50Ijp7InJvbGVzIjpbInZpZXctcmVhbG0iLCJ2aWV3LWlkZW50aXR5LXByb3ZpZGVycyIsIm1hbmFnZS1pZGVudGl0eS1wcm92aWRlcnMiLCJpbXBlcnNvbmF0aW9uIiwicmVhbG0tYWRtaW4iLCJjcmVhdGUtY2xpZW50IiwibWFuYWdlLXVzZXJzIiwicXVlcnktcmVhbG1zIiwidmlldy1hdXRob3JpemF0aW9uIiwicXVlcnktY2xpZW50cyIsInF1ZXJ5LXVzZXJzIiwibWFuYWdlLWV2ZW50cyIsIm1hbmFnZS1yZWFsbSIsInZpZXctZXZlbnRzIiwidmlldy11c2VycyIsInZpZXctY2xpZW50cyIsIm1hbmFnZS1hdXRob3JpemF0aW9uIiwibWFuYWdlLWNsaWVudHMiLCJxdWVyeS1ncm91cHMiXX0sImFjY291bnQiOnsicm9sZXMiOlsibWFuYWdlLWFjY291bnQiLCJtYW5hZ2UtYWNjb3VudC1saW5rcyIsInZpZXctcHJvZmlsZSJdfX0sInNjb3BlIjoicHJvZmlsZSBlbWFpbCIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJuYW1lIjoiYWRtaW4gcGdpY2huIiwicHJlZmVycmVkX3VzZXJuYW1lIjoiYWRtaW4iLCJnaXZlbl9uYW1lIjoiYWRtaW4iLCJmYW1pbHlfbmFtZSI6InBnaWNobiIsImVtYWlsIjoiYWRtaW4tcGdpY2huQG1lbmluZ2lvbWEuY29tIn0.ffucU6--Gi2mc5TxLsiWhKyL-Qp3yka1jsLjl8N_D3M-fvvKNNwIjxuPPpSPkyqQfvNnJYlrDi6E9uBTiwjkbywEjHIfefTGM6eMtYmc3fZFl4jTgEjujzeOQ2XOVpxb54KkiUcK7zqH5hq2Gdo36fzSUK6KFebyNB6RWDK_GAQMIBT5hxuvsNHDqTZ7BID14DE2kUq0HTHo2K8N1U0sIn1abpk2P0WUPXLo-eI9Pk_6B7O9VZOPl7E7nPzZFPZqwa9feWNBlhVTtiHsU0oCZHnp9fdnfttEVhRox6MEE3bpbgN11eO-HHjDJTE7rO6WbNoyj5eRWgrheLtfmGGBfA";
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
