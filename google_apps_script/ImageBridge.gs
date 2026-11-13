/**
 * Central Data Hub — Google Sheets Image Bridge
 *
 * Install this script from Extensions > Apps Script in an approved Google
 * Sheet. It NEVER changes cells in the spreadsheet. It creates a temporary
 * one-sheet copy, exports that copy to the Bridge Drive folder, then writes
 * a JSON manifest that Central Data Hub reads with its service account.
 * This avoids exporting an entire large spreadsheet and preserves images
 * positioned over cells as well as images inside cells.
 *
 * Before running:
 * 1) Create a new empty Google Drive folder for this source.
 * 2) Paste its ID below.
 * 3) Set SHEET_NAMES to the tabs that Central Data Hub has approved.
 * 4) Every imported tab must have a รูปภาพ column. The source Sheet is only
 *    read; the temporary copy is sent to the trash after export completes.
 */

const CONFIG = {
  DRIVE_FOLDER_ID: 'PASTE_DRIVE_FOLDER_ID_HERE',
  MANIFEST_FILE_NAME: 'central-data-hub-images.json',
  // Leave empty to process all tabs. Safer in production: list approved names.
  SHEET_NAMES: [],
  HEADER_ROW: 1,
  IMAGE_HEADERS: ['รูปภาพ', 'image_url', 'ลิงก์รูปภาพ', 'URL รูปภาพ'],
};


function exportCentralDataHubImages() {
  validateConfig_();
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const folder = DriveApp.getFolderById(CONFIG.DRIVE_FOLDER_ID);
  const oldManifest = readManifest_(folder);
  const result = { images: [], sheet_exports: [], issues: [] };
  const sheets = spreadsheet.getSheets().filter((sheet) =>
    !CONFIG.SHEET_NAMES.length || CONFIG.SHEET_NAMES.includes(sheet.getName())
  );

  sheets.forEach((sheet) => exportSheet_(sheet, folder, result));

  // Only retire copies named by the previous manifest after all current cells
  // have been inspected. Original Sheet cells and original images are never
  // deleted or edited.
  trashOldBridgeCopies_(oldManifest, bridgeFileIds_(result));

  const manifest = {
    version: 2,
    spreadsheet_id: spreadsheet.getId(),
    spreadsheet_name: spreadsheet.getName(),
    generated_at: new Date().toISOString(),
    images: result.images,
    sheet_exports: result.sheet_exports,
    issues: result.issues,
  };
  writeManifest_(folder, manifest);
  Logger.log(JSON.stringify({
    sheets_exported: result.sheet_exports.length,
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
  const imageColumn = findHeader_(headers, CONFIG.IMAGE_HEADERS);
  if (imageColumn < 0) {
    result.issues.push({
      sheet_name: sheet.getName(),
      kind: 'unconfigured_sheet',
      message: 'ไม่พบหัวคอลัมน์ รูปภาพ จึงข้ามชีตนี้',
    });
    return;
  }
  let temporary = null;
  try {
    temporary = SpreadsheetApp.create('Central Data Hub Bridge — ' + sheet.getName());
    const initialSheet = temporary.getSheets()[0];
    const copiedSheet = sheet.copyTo(temporary);
    temporary.deleteSheet(initialSheet);
    copiedSheet.setName(sheet.getName());
    SpreadsheetApp.flush();

    const mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    const exportUrl = 'https://www.googleapis.com/drive/v3/files/' + temporary.getId()
      + '/export?mimeType=' + encodeURIComponent(mimeType);
    const response = UrlFetchApp.fetch(exportUrl, {
      headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
      muteHttpExceptions: true,
    });
    if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
      throw new Error('export เป็น Excel ไม่สำเร็จ (HTTP ' + response.getResponseCode() + ')');
    }
    const filename = 'bridge-sheet__' + safeFileName_(sheet.getName()) + '.xlsx';
    const file = folder.createFile(response.getBlob().setName(filename));
    result.sheet_exports.push({
      sheet_name: sheet.getName(),
      header_row: CONFIG.HEADER_ROW,
      image_column: imageColumn + 1,
      drive_file_id: file.getId(),
      filename: filename,
    });
  } catch (error) {
    result.issues.push({
      sheet_name: sheet.getName(),
      kind: 'sheet_export_error',
      message: String(error),
    });
  } finally {
    if (temporary) {
      try { DriveApp.getFileById(temporary.getId()).setTrashed(true); }
      catch (error) { Logger.log('Cannot remove temporary workbook: ' + temporary.getId()); }
    }
  }
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
  if (!oldManifest) return;
  const oldFiles = (oldManifest.images || []).concat(oldManifest.sheet_exports || []);
  oldFiles.forEach((image) => {
    if (!image.drive_file_id || keep.has(image.drive_file_id)) return;
    try { DriveApp.getFileById(image.drive_file_id).setTrashed(true); }
    catch (error) { Logger.log('Cannot retire old bridge copy: ' + image.drive_file_id); }
  });
}

function bridgeFileIds_(result) {
  return result.images.concat(result.sheet_exports).map((item) => item.drive_file_id);
}
function normaliseHeader_(value) { return String(value || '').trim().toLowerCase(); }
function findHeader_(headers, candidates) {
  const wanted = candidates.map(normaliseHeader_);
  return headers.findIndex((header) => wanted.includes(header));
}
function safeFileName_(value) { return value.replace(/[\\/:*?"<>|]/g, '_'); }
function validateConfig_() {
  if (!CONFIG.DRIVE_FOLDER_ID || CONFIG.DRIVE_FOLDER_ID.includes('PASTE_')) {
    throw new Error('กรุณาตั้งค่า CONFIG.DRIVE_FOLDER_ID ก่อนรัน');
  }
}
