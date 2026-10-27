/**
 * Central Data Hub — Google Sheets Image Bridge
 *
 * Install this script from Extensions > Apps Script in an approved Google
 * Sheet. It NEVER changes cells in the spreadsheet. It copies supported
 * "image in cell" pictures to one Drive folder and writes a JSON manifest
 * that Central Data Hub later reads with its service account.
 *
 * Before running:
 * 1) Create a new empty Google Drive folder for this source.
 * 2) Paste its ID below.
 * 3) Set SHEET_NAMES to the tabs that Central Data Hub has approved.
 * 4) Ensure every imported row has a non-changing record_id.
 */

const CONFIG = {
  DRIVE_FOLDER_ID: 'PASTE_DRIVE_FOLDER_ID_HERE',
  MANIFEST_FILE_NAME: 'central-data-hub-images.json',
  // Leave empty to process all tabs. Safer in production: list approved names.
  SHEET_NAMES: [],
  HEADER_ROW: 1,
  RECORD_ID_HEADERS: ['record_id', 'Record ID', 'รหัสประจำรายการ', 'รหัสรายการ'],
  IMAGE_HEADERS: ['รูปภาพ', 'image_url', 'ลิงก์รูปภาพ', 'URL รูปภาพ'],
};


function exportCentralDataHubImages() {
  validateConfig_();
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const folder = DriveApp.getFolderById(CONFIG.DRIVE_FOLDER_ID);
  const oldManifest = readManifest_(folder);
  const result = { images: [], issues: [] };
  const sheets = spreadsheet.getSheets().filter((sheet) =>
    !CONFIG.SHEET_NAMES.length || CONFIG.SHEET_NAMES.includes(sheet.getName())
  );

  sheets.forEach((sheet) => exportSheet_(sheet, folder, result));

  // Only retire copies named by the previous manifest after all current cells
  // have been inspected. Original Sheet cells and original images are never
  // deleted or edited.
  trashOldBridgeCopies_(oldManifest, result.images.map((image) => image.drive_file_id));

  const manifest = {
    version: 1,
    spreadsheet_id: spreadsheet.getId(),
    spreadsheet_name: spreadsheet.getName(),
    generated_at: new Date().toISOString(),
    images: result.images,
    issues: result.issues,
  };
  writeManifest_(folder, manifest);
  Logger.log(JSON.stringify({
    images_exported: result.images.length,
    issues: result.issues.length,
    manifest: CONFIG.MANIFEST_FILE_NAME,
  }, null, 2));
}


function exportSheet_(sheet, folder, result) {
  const lastColumn = sheet.getLastColumn();
  const lastRow = sheet.getLastRow();
  if (!lastColumn || lastRow <= CONFIG.HEADER_ROW) return;

  const headers = sheet.getRange(CONFIG.HEADER_ROW, 1, 1, lastColumn)
    .getDisplayValues()[0].map(normaliseHeader_);
  const recordIdColumn = findHeader_(headers, CONFIG.RECORD_ID_HEADERS);
  const imageColumn = findHeader_(headers, CONFIG.IMAGE_HEADERS);
  if (recordIdColumn < 0 || imageColumn < 0) {
    result.issues.push({
      sheet_name: sheet.getName(),
      kind: 'unconfigured_sheet',
      message: 'ไม่พบหัวคอลัมน์ record_id หรือ รูปภาพ จึงข้ามชีตนี้',
    });
    return;
  }

  const rowCount = lastRow - CONFIG.HEADER_ROW;
  const recordIds = sheet.getRange(CONFIG.HEADER_ROW + 1, recordIdColumn + 1, rowCount, 1)
    .getDisplayValues().flat();
  const imageCells = sheet.getRange(CONFIG.HEADER_ROW + 1, imageColumn + 1, rowCount, 1);
  const cellValues = imageCells.getValues();

  cellValues.forEach((row, index) => {
    const recordId = String(recordIds[index] || '').trim();
    const rowNumber = CONFIG.HEADER_ROW + 1 + index;
    if (!recordId) return;
    const value = row[0];
    if (!isCellImage_(value)) return;
    try {
      const blob = UrlFetchApp.fetch(value.getContentUrl()).getBlob();
      const extension = extensionForBlob_(blob);
      const filename = safeFileName_(recordId) + '__1' + extension;
      const file = folder.createFile(blob.setName(filename));
      result.images.push({
        record_id: recordId,
        sheet_name: sheet.getName(),
        source_row_number: rowNumber,
        kind: 'in_cell',
        position: 1,
        drive_file_id: file.getId(),
        filename: filename,
      });
    } catch (error) {
      result.issues.push({
        sheet_name: sheet.getName(),
        record_id: recordId,
        source_row_number: rowNumber,
        kind: 'in_cell_error',
        message: String(error),
      });
    }
  });

  // Google calls these "over-grid" images. Their source URLs are deprecated
  // and not consistently available, so this script records their location for
  // review instead of guessing or changing the Sheet.
  sheet.getImages().forEach((image) => {
    const anchor = image.getAnchorCell();
    if (anchor.getColumn() !== imageColumn + 1 || anchor.getRow() <= CONFIG.HEADER_ROW) return;
    const index = anchor.getRow() - CONFIG.HEADER_ROW - 1;
    result.issues.push({
      sheet_name: sheet.getName(),
      record_id: String(recordIds[index] || '').trim() || null,
      source_row_number: anchor.getRow(),
      kind: 'over_grid',
      message: 'พบรูปลอยทับเซลล์: ระบบบันทึกตำแหน่งไว้ แต่ยังไม่คัดลอกอัตโนมัติ',
    });
  });
}


function readManifest_(folder) {
  const files = folder.getFilesByName(CONFIG.MANIFEST_FILE_NAME);
  if (!files.hasNext()) return null;
  try { return JSON.parse(files.next().getBlob().getDataAsString('UTF-8')); }
  catch (error) { return null; }
}

function writeManifest_(folder, manifest) {
  const files = folder.getFilesByName(CONFIG.MANIFEST_FILE_NAME);
  while (files.hasNext()) files.next().setTrashed(true);
  folder.createFile(CONFIG.MANIFEST_FILE_NAME, JSON.stringify(manifest, null, 2), MimeType.PLAIN_TEXT);
}


function trashOldBridgeCopies_(oldManifest, newFileIds) {
  const keep = new Set(newFileIds);
  if (!oldManifest || !Array.isArray(oldManifest.images)) return;
  oldManifest.images.forEach((image) => {
    if (!image.drive_file_id || keep.has(image.drive_file_id)) return;
    try { DriveApp.getFileById(image.drive_file_id).setTrashed(true); }
    catch (error) { Logger.log('Cannot retire old bridge copy: ' + image.drive_file_id); }
  });
}


function isCellImage_(value) {
  return value && typeof value.getContentUrl === 'function';
}
function normaliseHeader_(value) { return String(value || '').trim().toLowerCase(); }
function findHeader_(headers, candidates) {
  const wanted = candidates.map(normaliseHeader_);
  return headers.findIndex((header) => wanted.includes(header));
}
function safeFileName_(value) { return value.replace(/[\\/:*?"<>|]/g, '_'); }
function extensionForBlob_(blob) {
  const mime = String(blob.getContentType() || '').toLowerCase();
  if (mime === 'image/png') return '.png';
  if (mime === 'image/gif') return '.gif';
  if (mime === 'image/webp') return '.webp';
  return '.jpg';
}
function validateConfig_() {
  if (!CONFIG.DRIVE_FOLDER_ID || CONFIG.DRIVE_FOLDER_ID.includes('PASTE_')) {
    throw new Error('กรุณาตั้งค่า CONFIG.DRIVE_FOLDER_ID ก่อนรัน');
  }
}
