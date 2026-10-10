/**
 * aiwolf-nlp-organizer-tool: 参加登録フォームの生成（共通部分）。
 * Code.js（ops form create が生成）が SPECS と createForm_<大会 id>() を定義する。
 * 返り値は JSON 文字列。clasp run の戻り値、またはログから Python 側が読む。
 */
function createFormFor(cid) {
  const spec = SPECS[cid];
  if (!spec) throw new Error('unknown contest: ' + cid);
  const form = FormApp.create(spec.title);
  if (spec.description) form.setDescription(spec.description);
  form.setCollectEmail(false);
  spec.questions.forEach(q => addItem_(form, q));

  // 回答先シート
  const ss = SpreadsheetApp.create(spec.title + ' (回答)');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  // 読み取り用サービスアカウントへ共有（指定があれば）
  if (spec.share_with) {
    spec.share_with.forEach(addr => { try { ss.addViewer(addr); } catch (e) { Logger.log('share failed: ' + addr + ' ' + e); } });
  }
  // 公開・受付開始（新しい Forms では公開操作が必要。無い環境では無視）
  try { if (typeof form.setPublished === 'function') form.setPublished(true); } catch (e) { Logger.log('setPublished: ' + e); }
  try { form.setAcceptingResponses(true); } catch (e) { Logger.log('setAcceptingResponses: ' + e); }

  const result = {
    form_id: form.getId(),
    form_edit_url: form.getEditUrl(),
    form_url: form.getPublishedUrl(),
    sheet_id: ss.getId(),
    sheet_url: ss.getUrl(),
  };
  Logger.log('RESULT ' + JSON.stringify(result));
  return JSON.stringify(result);
}

function addItem_(form, q) {
  let item;
  switch (q.type) {
    case 'text': item = form.addTextItem(); break;
    case 'paragraph': item = form.addParagraphTextItem(); break;
    case 'radio': item = form.addMultipleChoiceItem(); break;
    case 'checkbox': item = form.addCheckboxItem(); break;
    case 'dropdown': item = form.addListItem(); break;
    default: throw new Error('unknown type: ' + q.type);
  }
  item.setTitle(q.label);
  if (q.help) item.setHelpText(q.help);
  if (q.required) item.setRequired(true);
  if (q.options) item.setChoices(q.options.map(v => item.createChoice(v)));
  return item;
}

function ping() { return "pong " + new Date().toISOString(); }

/** ウェブアプリ経由の実行口（clasp run が使えない環境用）。 ?fn=ping / ?fn=createForm&cid=<大会 id> */
function doGet(e) {
  const p = (e && e.parameter) || {};
  let out;
  try {
    if (p.fn === 'ping') out = { ok: true, result: ping() };
    else if (p.fn === 'createForm') out = { ok: true, result: JSON.parse(createFormFor(p.cid)) };
    else if (p.fn === 'sharePublic') { DriveApp.getFileById(p.file_id).setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW); out = { ok: true, result: { public: true } }; }
    else if (p.fn === 'share') { SpreadsheetApp.openById(p.file_id).addViewer(p.email); out = { ok: true, result: { shared: p.email } }; }
    else out = { ok: false, error: 'unknown fn' };
  } catch (err) { out = { ok: false, error: String(err) }; }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

/** POST 版の実行口（本文が長いもの用）。body: {fn, ...} */
function doPost(e) {
  let out;
  try {
    const p = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (p.fn === 'upsertGrid') out = { ok: true, result: upsertGrid(p.spec) };
    else out = { ok: false, error: 'unknown fn' };
  } catch (err) { out = { ok: false, error: String(err && err.stack || err) }; }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}



/** エディタで一度だけ実行する: 必要な権限（フォーム・スプレッドシート・ドライブ）の承認画面を出すためだけの関数 */
function authorize() {
  const n = DriveApp.getRootFolder().getName();
  const s = SpreadsheetApp.create('ops-authorize-check'); DriveApp.getFileById(s.getId()).setTrashed(true);
  Logger.log('ok: drive=' + n);
  return 'ok';
}

/** 大会定義シート（行 = 項目、列 = 大会）。spec: {book_id?, title, share_with, public, tabs:[{name, header, rows, widths, freeze_rows, freeze_cols,
 *  col_groups:[{start,end,collapsed}], validations:[{row,row_end?,col_start,col_end,type,values}], bg:[{row,cols,color,bold}], required:[{row,col_start,col_end}], protect, wrap, keep_existing}]} */
function upsertGrid(spec) {
  const ss = spec.book_id ? SpreadsheetApp.openById(spec.book_id) : SpreadsheetApp.create(spec.title);
  spec.tabs.forEach(tab => {
    let sh = ss.getSheetByName(tab.name);
    if (sh && tab.keep_existing) return;
    if (sh) ss.deleteSheet(sh);
    sh = ss.insertSheet(tab.name);
    const ncol = tab.header.length, nrow = tab.rows.length + 1;
    sh.getRange(1, 1, 1, ncol).setValues([tab.header]).setFontWeight('bold').setBackground('#e8eaed');
    if (tab.rows.length) sh.getRange(2, 1, tab.rows.length, ncol).setValues(tab.rows);
    if (tab.freeze_rows) sh.setFrozenRows(tab.freeze_rows);
    if (tab.freeze_cols) sh.setFrozenColumns(tab.freeze_cols);
    (tab.widths || []).forEach((w, j) => { if (w) sh.setColumnWidth(j + 1, w); });
    if (tab.wrap) sh.getRange(1, 1, nrow, ncol).setWrap(true).setVerticalAlignment('top');
    (tab.validations || []).forEach(v => {
      let rule = null;
      if (v.type === 'list') rule = SpreadsheetApp.newDataValidation().requireValueInList(v.values, true).setAllowInvalid(false).build();
      else if (v.type === 'checkbox') rule = SpreadsheetApp.newDataValidation().requireCheckbox().build();
      if (!rule) return;
      const r0 = v.row, nr = (v.row_end || v.row) - v.row + 1, c0 = v.col_start || v.col, nc = (v.col_end || c0) - c0 + 1;
      sh.getRange(r0, c0, nr, nc).setDataValidation(rule);
    });
    (tab.bg || []).forEach(b => { const r = sh.getRange(b.row, 1, 1, b.cols || 1); r.setBackground(b.color); if (b.bold) r.setFontWeight('bold'); });
    if (tab.required && tab.required.length) {
      const ranges = tab.required.map(q => sh.getRange(q.row, q.col_start, 1, q.col_end - q.col_start + 1));
      sh.setConditionalFormatRules([SpreadsheetApp.newConditionalFormatRule().whenCellEmpty().setBackground('#f8d7da').setRanges(ranges).build()]);
    }
    (tab.col_groups || []).forEach(g => {
      const rg = sh.getRange(1, g.start, 1, g.end - g.start + 1);
      rg.shiftColumnGroupDepth(1);
      if (g.collapsed) { try { sh.getColumnGroup(g.start, 1).collapse(); } catch (e) {} }
    });
    if (tab.protect) { const pr = sh.getRange(tab.protect).protect(); pr.setWarningOnly(true); pr.setDescription('項目・キー・説明の列。値は大会の列に入力'); }
  });
  // タブの並び: 大会, 大会_en, トラック, トラック_en, ルール
  ['ルール', 'トラック_en', 'トラック', '大会_en', '大会'].forEach(n => { const sh = ss.getSheetByName(n); if (sh) { ss.setActiveSheet(sh); ss.moveActiveSheet(1); } });
  const def = ss.getSheetByName('シート1') || ss.getSheetByName('Sheet1');
  if (def && ss.getSheets().length > 1) ss.deleteSheet(def);
  (spec.drop_tabs || []).forEach(n => { const s = ss.getSheetByName(n); if (s && ss.getSheets().length > 1) ss.deleteSheet(s); });
  (spec.share_with || []).forEach(addr => { try { ss.addViewer(addr); } catch (e) {} });
  if (spec.public) { try { DriveApp.getFileById(ss.getId()).setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW); } catch (e) {} }
  return { book_id: ss.getId(), book_url: ss.getUrl(), tabs: ss.getSheets().map(s => s.getName()) };
}
