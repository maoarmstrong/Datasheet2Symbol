import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const sourcePath = process.argv[2];
const outputDir = process.argv[3];
const maxPinsPerSection = 100;

if (!sourcePath || !outputDir) {
  throw new Error("Usage: node build_orcad_fpga_pinlist.mjs <ascii-pinout.txt> <output-dir>");
}

const text = await fs.readFile(sourcePath, "utf8");
const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/);
const deviceMatch = text.match(/^--\s+Device\s+:\s+(\S+)/m);
const deviceName = (deviceMatch?.[1] ?? "FPGA").toUpperCase();
const headerIndex = lines.findIndex((line) => /^Pin\s+Pin Name\s+Memory Byte Group\s+Bank\s+I\/O Type/.test(line));
if (headerIndex < 0) throw new Error("Could not find the ASCII Pinout table header.");

const pins = [];
for (const line of lines.slice(headerIndex + 1)) {
  if (!/^\S+\s{2,}\S+/.test(line)) continue;
  const fields = line.trim().split(/\s{2,}/);
  if (fields.length < 5) continue;
  pins.push({ pin: fields[0], name: fields[1], memoryByteGroup: fields[2], bank: fields[3], ioType: fields[4] });
}
if (!pins.length) throw new Error("No pin rows were parsed.");

const isGround = (name) => /(^|_)(GND|VSS)(_|$)|RSVDGND|GNDADC/.test(name);
const isPower = (name) => /^(VCC|VDD|AVCC|VCCAUX|VCCO|VBATT)|^VREF_/.test(name);
const isConfig = (pin) => pin.ioType === "CONFIG";

function electricalType(pin) {
  if (isGround(pin.name) || isPower(pin.name)) return "Power";
  if (/^(DONE|TDO)_/.test(pin.name)) return "Output";
  if (/^IO_/.test(pin.name)) return "Bidirectional";
  return "Input";
}

function position(pin, type) {
  if (isGround(pin.name)) return "Bottom";
  if (isPower(pin.name)) return "Top";
  return type === "Output" ? "Right" : "Left";
}

function functionalGroup(pin) {
  if (isGround(pin.name)) return "GROUND";
  if (isPower(pin.name)) return "POWER";
  if (isConfig(pin)) return "CONFIG";
  if (pin.bank !== "NA") return `BANK_${pin.bank}`;
  return "CONTROL_ANALOG";
}

const groupOrder = (name) => {
  if (name === "CONFIG") return 0;
  if (/^BANK_\d+$/.test(name)) return 10 + Number(name.slice(5));
  if (name === "CONTROL_ANALOG") return 900;
  if (name === "POWER") return 910;
  if (name === "GROUND") return 920;
  return 999;
};

function sectionName(index) {
  let n = index;
  let out = "";
  do {
    out = String.fromCharCode(65 + (n % 26)) + out;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return out;
}

const grouped = new Map();
for (const pin of pins) {
  const group = functionalGroup(pin);
  if (!grouped.has(group)) grouped.set(group, []);
  grouped.get(group).push(pin);
}

const sections = [];
for (const [group, groupPins] of [...grouped.entries()].sort(([a], [b]) => groupOrder(a) - groupOrder(b) || a.localeCompare(b))) {
  for (let start = 0; start < groupPins.length; start += maxPinsPerSection) {
    sections.push({
      section: sectionName(sections.length),
      group,
      pins: groupPins.slice(start, start + maxPinsPerSection),
    });
  }
}

const orcadRows = [];
const auditRows = [];
for (const section of sections) {
  for (const pin of section.pins) {
    const type = electricalType(pin);
    const row = [pin.pin, pin.name, type, "1", "Line", "", position(pin, type), section.section];
    orcadRows.push(row);
    auditRows.push([...row, pin.memoryByteGroup, pin.bank, pin.ioType, section.group, "All pins: select in OrCAD"]);
  }
}

const wb = Workbook.create();
const pasteSheet = wb.worksheets.add("Paste_To_OrCAD");
const summarySheet = wb.worksheets.add("Section_Summary");
const auditSheet = wb.worksheets.add("Source_Audit");

pasteSheet.showGridLines = false;
pasteSheet.getRange("A1:H1").values = [["Number", "Name", "Type", "Pin Visibility", "Shape", "PinGroup", "Position", "Section"]];
pasteSheet.getRangeByIndexes(1, 0, orcadRows.length, 8).values = orcadRows;
pasteSheet.getRange(`A1:H${orcadRows.length + 1}`).format.font = { name: "Arial", size: 10 };
pasteSheet.getRange("A1:H1").format = { fill: "#1F4E78", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center" };
pasteSheet.getRange(`A1:H${orcadRows.length + 1}`).format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
pasteSheet.freezePanes.freezeRows(1);
const pasteWidths = [12, 42, 16, 16, 12, 14, 14, 11];
for (let i = 0; i < pasteWidths.length; i++) pasteSheet.getRangeByIndexes(0, i, orcadRows.length + 1, 1).format.columnWidth = pasteWidths[i];

summarySheet.showGridLines = false;
summarySheet.getRange("A1:B1").merge();
summarySheet.getRange("A1").values = [[`${deviceName} — OrCAD Section Plan`]];
summarySheet.getRange("A1").format = { font: { name: "Arial", size: 14, bold: true, color: "#1F1F1F" } };
summarySheet.getRange("A3:B7").values = [
  ["Part Name", deviceName],
  ["Part Ref Prefix", "U"],
  ["Part Numbering", "Alphabetic"],
  ["No. of Sections", sections.length],
  ["Maximum pins / section", maxPinsPerSection],
];
summarySheet.getRange("A9:D9").values = [["Section", "Functional group", "Pins", "OrCAD action"]];
summarySheet.getRangeByIndexes(9, 0, sections.length, 4).values = sections.map((section) => [section.section, section.group, section.pins.length, "Paste rows; select all Pin Visibility check boxes"]);
summarySheet.getRange("A9:D9").format = { fill: "#1F4E78", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center" };
summarySheet.getRange(`A9:D${sections.length + 9}`).format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
summarySheet.getRange("A12").values = [["Copy only the data rows from Paste_To_OrCAD (not the header), paste into the top-left Number cell, then select every Pin Visibility check box in Capture."]];
summarySheet.getRange("A12:D12").merge();
summarySheet.getRange("A12").format = { font: { name: "Arial", size: 10, italic: true, color: "#595959" }, wrapText: true };
summarySheet.getRange("A:A").format.columnWidth = 18;
summarySheet.getRange("B:B").format.columnWidth = 24;
summarySheet.getRange("C:C").format.columnWidth = 12;
summarySheet.getRange("D:D").format.columnWidth = 50;
summarySheet.getRange("A12").format.rowHeight = 34;

auditSheet.showGridLines = false;
const auditHeaders = ["Number", "Name", "Type", "Pin Visibility", "Shape", "PinGroup", "Position", "Section", "Memory Byte Group", "Bank", "I/O Type", "Functional Group", "Visibility Requirement"];
auditSheet.getRangeByIndexes(0, 0, 1, auditHeaders.length).values = [auditHeaders];
auditSheet.getRangeByIndexes(1, 0, auditRows.length, auditHeaders.length).values = auditRows;
auditSheet.getRange(`A1:M${auditRows.length + 1}`).format.font = { name: "Arial", size: 10 };
auditSheet.getRange("A1:M1").format = { fill: "#5B9BD5", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center" };
auditSheet.freezePanes.freezeRows(1);
auditSheet.getRange(`A1:M${auditRows.length + 1}`).format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
const auditWidths = [12, 42, 16, 16, 12, 14, 14, 11, 18, 10, 12, 20, 28];
for (let i = 0; i < auditWidths.length; i++) auditSheet.getRangeByIndexes(0, i, auditRows.length + 1, 1).format.columnWidth = auditWidths[i];

wb.recalculate();
const duplicatePins = new Set();
const seenPins = new Set();
for (const row of orcadRows) {
  if (seenPins.has(row[0])) duplicatePins.add(row[0]);
  seenPins.add(row[0]);
}
if (orcadRows.length !== pins.length) throw new Error(`Pin count mismatch: ${pins.length} source vs ${orcadRows.length} output.`);
if (duplicatePins.size) throw new Error(`Duplicate pin numbers: ${[...duplicatePins].join(", ")}`);
if (sections.some((section) => section.pins.length > maxPinsPerSection)) throw new Error("Section height limit exceeded.");

await fs.mkdir(outputDir, { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(path.join(outputDir, `${deviceName}_OrCAD_Pinlist.xlsx`));

const preview = await wb.render({ sheetName: "Paste_To_OrCAD", range: "A1:H25", scale: 1.4, format: "png" });
await fs.writeFile(path.join(outputDir, "paste_preview.png"), new Uint8Array(await preview.arrayBuffer()));

console.log(JSON.stringify({ deviceName, sourcePins: pins.length, outputPins: orcadRows.length, sections: sections.map(({ section, group, pins: sectionPins }) => ({ section, group, count: sectionPins.length })), output: path.join(outputDir, `${deviceName}_OrCAD_Pinlist.xlsx`) }, null, 2));
