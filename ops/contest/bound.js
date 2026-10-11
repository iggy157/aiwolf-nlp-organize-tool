/**
 * 大会定義シートに紐づくスクリプト（ops contest button が生成して push する。直接編集しない）。
 * メニュー「大会データ → 大会データを更新」で、シートの中身を圧縮して GitHub の __REPO__ の Actions（import-sheet.yml）に渡し、
 * contest.yaml に書いて push させる。シートは非公開のままでよい。結果（変更・警告）をダイアログで表示する。
 * GitHub のトークンは押す人ごとに保存する（ユーザープロパティ。他の人からは見えない）。
 */
const REPO = '__REPO__';
const REF = '__REF__';
const WORKFLOW = 'import-sheet.yml';

function onOpen() {
  SpreadsheetApp.getUi().createMenu('大会データ')
    .addItem('大会データを更新', 'updateData')
    .addSeparator()
    .addItem('GitHub のトークンを設定', 'setToken')
    .addItem('最近の更新を見る', 'openActions')
    .addToUi();
}

function setToken() {
  const ui = SpreadsheetApp.getUi();
  const r = ui.prompt('GitHub のトークン',
    'fine-grained personal access token を貼ってください。\n対象リポジトリ: ' + REPO + '\n権限: Actions を Read and write（ほかは不要）\n保存先はあなた専用の領域で、他の人には見えません。',
    ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton() !== ui.Button.OK) return null;
  const tok = r.getResponseText().trim();
  if (!tok) return null;
  PropertiesService.getUserProperties().setProperty('GITHUB_TOKEN', tok);
  ui.alert('保存しました。');
  return tok;
}

function openActions() {
  const url = 'https://github.com/' + REPO + '/actions/workflows/' + WORKFLOW;
  const html = HtmlService.createHtmlOutput('<p><a href="' + url + '" target="_blank">' + url + '</a></p>').setWidth(520).setHeight(80);
  SpreadsheetApp.getUi().showModalDialog(html, '最近の更新');
}

function gh_(method, path, tok, body) {
  const opt = { method: method, muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + tok, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' } };
  if (body) { opt.contentType = 'application/json'; opt.payload = JSON.stringify(body); }
  const res = UrlFetchApp.fetch('https://api.github.com' + path, opt);
  const text = res.getContentText();
  return { code: res.getResponseCode(), json: text ? (function () { try { return JSON.parse(text); } catch (e) { return text; } })() : null };
}

function updateData() {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActive();
  let tok = PropertiesService.getUserProperties().getProperty('GITHUB_TOKEN') || setToken();
  if (!tok) return;
  SpreadsheetApp.flush();
  // シートの中身をそのまま渡す（Actions はシートを読みに行かないので、シートを非公開にできる）
  const gids = {}, grids = {};
  ss.getSheets().forEach(s => {
    gids[s.getName()] = s.getSheetId();
    if (['大会', '大会_en', 'トラック', 'トラック_en', 'ルール'].indexOf(s.getName()) >= 0) grids[s.getName()] = s.getDataRange().getDisplayValues();
  });
  const payload = Utilities.base64Encode(Utilities.gzip(Utilities.newBlob(JSON.stringify(grids), 'application/json')).getBytes());
  if (payload.length > 60000) { ui.alert('シートの中身が大きすぎて送れません（' + payload.length + ' 文字）。管理者に連絡してください。'); return; }
  let actor = '';
  try { actor = Session.getActiveUser().getEmail(); } catch (e) {}
  const started = Date.now();
  const d = gh_('post', '/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches', tok,
    { ref: REF, inputs: { book_id: ss.getId(), gids: JSON.stringify(gids), payload: payload, actor: actor } });
  if (d.code !== 204) {
    const hint = (d.code === 401 || d.code === 403 || d.code === 404) ? '\n\nトークンが無効か、権限（Actions: Read and write）が足りません。メニューの「GitHub のトークンを設定」でやり直してください。' : '';
    ui.alert('更新を始められませんでした（' + d.code + '）\n' + JSON.stringify(d.json).slice(0, 300) + hint);
    return;
  }
  ss.toast('GitHub で更新中です（30 秒〜1 分）。このまま待ってください。', '大会データ', 90);
  let run = null;
  for (let i = 0; i < 36; i++) {          // 最大 3 分待つ
    Utilities.sleep(5000);
    const r = gh_('get', '/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/runs?event=workflow_dispatch&per_page=5', tok);
    const runs = (r.json && r.json.workflow_runs) || [];
    run = runs.find(x => new Date(x.created_at).getTime() >= started - 15000) || null;
    if (run && run.status === 'completed') break;
  }
  if (!run || run.status !== 'completed') {
    ui.alert('まだ終わっていません。少し待ってから「最近の更新を見る」で確認してください。');
    return;
  }
  // 警告（未記入の必須項目など）は Actions の注釈から拾う
  let notes = [];
  const jobs = gh_('get', '/repos/' + REPO + '/actions/runs/' + run.id + '/jobs', tok);
  ((jobs.json && jobs.json.jobs) || []).forEach(j => {
    const an = gh_('get', '/repos/' + REPO + '/check-runs/' + j.id + '/annotations', tok);
    ((Array.isArray(an.json) && an.json) || []).forEach(a => { if (a.annotation_level === 'warning') notes.push('・' + a.message); });
  });
  let msg;
  if (run.conclusion === 'success') {
    const c = gh_('get', '/repos/' + REPO + '/commits?sha=' + REF + '&per_page=1', tok);
    const head = (c.json && c.json[0]) || null;
    const fresh = head && new Date(head.commit.committer.date).getTime() >= started - 15000;
    msg = fresh ? '更新しました。\n' + head.commit.message : '変更はありませんでした（シートと contest-data は同じです）。';
    msg += '\n\nサイトに反映するには、aiwolf-nlp で取り込み（sync.sh）→ localhost で確認 → push です。';
  } else {
    msg = '更新に失敗しました（' + run.conclusion + '）。詳細: ' + run.html_url;
  }
  if (notes.length) msg += '\n\n注意:\n' + notes.filter(n => !/Node\.js|deprecated/i.test(n)).join('\n');
  ui.alert('大会データ', msg, ui.ButtonSet.OK);
}
