const XLSX = require("xlsx");
const fs = require("fs");
const path = require("path");

// List your yellow (group header) columns here:
const yellowHeaders = [
  "SUBJECT INFORMATION",
  "PRESENTING COMPLAINTS",
  "MEDICAL HISTORY",
  "PAST TREATMENT HISTORY",
  "FAMILY HISTORY",
  "PATIENT INVESTIGATION RADIOLOGICAL DETAILS",
  "MRI AND CT FINDING",
  "OPERATIVE DETAILS",
  "HISTOPATHOLOGICAL DETAILS",
  "OUT COME AND POST OF FOLLOW UP",
];

const inputPath = process.argv[2] || "00055AIIMSD150323.xlsx";
const sheetNameArg = process.argv[3]; // optional

if (!fs.existsSync(inputPath)) {
  console.error(`❌ File not found: ${inputPath}`);
  process.exit(1);
}

const ext = path.extname(inputPath).toLowerCase();
let rows = [],
  headers = [];

function getGroupedHeaders(headerRow) {
  let groups = {};
  let currentGroup = null;
  // Prepare lowercase set for faster case-insensitive matching
  const yellowSet = new Set(yellowHeaders.map((h) => h.toLowerCase()));

  headerRow.forEach((header, ix) => {
    const headerLower = (header || "").toString().trim().toLowerCase();
    if (yellowSet.has(headerLower)) {
      // Match found regardless of case
      currentGroup = header;
      groups[currentGroup] = [];
    } else if (currentGroup) {
      groups[currentGroup].push({ name: header, ix });
    }
  });
  return groups;
}

function groupRow(rowArr, groups, headerRow) {
  let result = {};
  let usedIndices = new Set();

  // Attach non-group columns (outside yellow header region)
  headerRow.forEach((header, ix) => {
    if (
      !Object.keys(groups).some((gh) => gh === header) &&
      !Object.values(groups)
        .flat()
        .some((g) => g.ix === ix)
    ) {
      result[header] = rowArr[ix];
      usedIndices.add(ix);
    }
  });

  // Attach group columns
  for (let g of Object.keys(groups)) {
    let groupObj = {};
    for (let { name, ix } of groups[g]) {
      groupObj[name] = rowArr[ix];
      usedIndices.add(ix);
    }
    result[g] = groupObj;
  }
  return result;
}

// --- Handle .xlsx or .xls files ---
if (ext === ".xlsx" || ext === ".xls") {
  const wb = XLSX.readFile(inputPath, { cellDates: true });
  const sheetName = sheetNameArg || wb.SheetNames[0];
  const ws = wb.Sheets[sheetName];
  if (!ws) {
    console.error(`❌ Sheet not found: ${sheetName}`);
    process.exit(1);
  }

  // Parse raw rows for grouping
  const range = XLSX.utils.decode_range(ws["!ref"]);
  // get header row
  let headerRow = [];
  for (let c = range.s.c; c <= range.e.c; ++c) {
    let cell = ws[XLSX.utils.encode_cell({ r: range.s.r, c })];
    headerRow.push(cell ? cell.v : "");
  }

  const groups = getGroupedHeaders(headerRow);
  for (let r = range.s.r + 1; r <= range.e.r; ++r) {
    let rowArr = [];
    for (let c = range.s.c; c <= range.e.c; ++c) {
      let cell = ws[XLSX.utils.encode_cell({ r, c })];
      rowArr.push(cell ? cell.v : null);
    }
    if (rowArr.every((v) => v === null || v === "")) continue; // skip empty rows
    rows.push(groupRow(rowArr, groups, headerRow));
  }
} else if (ext === ".csv") {
  // For CSV, use the XLSX .read API
  const csvData = fs.readFileSync(inputPath, "utf8");
  const wb = XLSX.read(csvData, { type: "string" }); // parse CSV as workbook
  const ws = wb.Sheets[wb.SheetNames[0]]; // first sheet
  // Parse as above
  const range = XLSX.utils.decode_range(ws["!ref"]);
  // get header row
  let headerRow = [];
  for (let c = range.s.c; c <= range.e.c; ++c) {
    let cell = ws[XLSX.utils.encode_cell({ r: range.s.r, c })];
    headerRow.push(cell ? cell.v : "");
  }
  const groups = getGroupedHeaders(headerRow);
  for (let r = range.s.r + 1; r <= range.e.r; ++r) {
    let rowArr = [];
    for (let c = range.s.c; c <= range.e.c; ++c) {
      let cell = ws[XLSX.utils.encode_cell({ r, c })];
      rowArr.push(cell ? cell.v : null);
    }
    if (rowArr.every((v) => v === null || v === "")) continue;
    rows.push(groupRow(rowArr, groups, headerRow));
  }
} else {
  console.error("❌ Unsupported file type. Use .xlsx, .xls, or .csv");
  process.exit(1);
}

// --- Output JSON ---
const jsonString = JSON.stringify(rows, null, 2);
// process.stdout.write(jsonString);
// Save JSON to file
const outputFile = path.join(process.cwd(), "output.json");
fs.writeFileSync(outputFile, jsonString, "utf8");
console.log(`✅ JSON saved to ${outputFile}`);
