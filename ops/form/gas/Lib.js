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
    if (p.fn === 'upsertTabs') out = { ok: true, result: upsertDefinitionTabs(p.spec) };
    else out = { ok: false, error: 'unknown fn' };
  } catch (err) { out = { ok: false, error: String(err && err.stack || err) }; }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}


/** 大会定義シート（1 冊）。spec: {book_id?, title, share_with:[], tabs:[{name, header, rows, widths, validations, bg:[{row,cols,color,bold}], collapse:'C:E', protect:'A:A,C:E'}]}
 *  book_id が無ければ新しく作る。同名のタブがあれば置き換える。 */
function upsertDefinitionTabs(spec) {
  const ss = spec.book_id ? SpreadsheetApp.openById(spec.book_id) : SpreadsheetApp.create(spec.title);
  spec.tabs.forEach(tab => {
    let sh = ss.getSheetByName(tab.name);
    if (sh) { ss.deleteSheet(sh); }
    sh = ss.insertSheet(tab.name);
    const ncol = tab.header.length;
    sh.getRange(1, 1, 1, ncol).setValues([tab.header]).setFontWeight('bold').setBackground('#e8eaed');
    if (tab.rows.length) sh.getRange(2, 1, tab.rows.length, ncol).setValues(tab.rows);
    sh.setFrozenRows(1);
    (tab.widths || []).forEach((w, j) => { if (w) sh.setColumnWidth(j + 1, w); });
    sh.getRange(1, 1, tab.rows.length + 1, ncol).setWrap(true).setVerticalAlignment('top');
    (tab.validations || []).forEach(v => {
      let rule = null;
      if (v.type === 'list') rule = SpreadsheetApp.newDataValidation().requireValueInList(v.values, true).setAllowInvalid(false).build();
      else if (v.type === 'date') rule = SpreadsheetApp.newDataValidation().requireDate().setAllowInvalid(true).setHelpText('日付（例 2027/07/04）').build();
      else if (v.type === 'checkbox') rule = SpreadsheetApp.newDataValidation().requireCheckbox().build();
      if (rule) sh.getRange(v.row, v.col).setDataValidation(rule);
    });
    (tab.bg || []).forEach(b => { const r = sh.getRange(b.row, 1, 1, b.cols || 1); r.setBackground(b.color); if (b.bold) r.setFontWeight('bold'); });
    if (tab.collapse) { sh.getRange(tab.collapse).setBackground('#f8f9fa').setFontColor('#5f6368'); sh.getRange(tab.collapse).shiftColumnGroupDepth(1); sh.collapseAllColumnGroups(); }
    (tab.protect || '').split(',').filter(Boolean).forEach(a1 => { const pr = sh.getRange(a1).protect(); pr.setWarningOnly(true); pr.setDescription('値は B 列に入力。この列は変えない'); });
  });
  // 既定の空シートが残っていれば消す
  const def = ss.getSheetByName('シート1') || ss.getSheetByName('Sheet1');
  if (def && ss.getSheets().length > 1) ss.deleteSheet(def);
  (spec.share_with || []).forEach(addr => { try { ss.addViewer(addr); } catch (e) {} });
  return { book_id: ss.getId(), book_url: ss.getUrl(), tabs: spec.tabs.map(t => t.name) };
}
