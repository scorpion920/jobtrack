/* Читач сторінки «Відгуки на вакансії» на jobs.dou.ua.
 *
 * DOU, на відміну від Djinni, НЕ показує стану відгуку: лише факт подачі,
 * дату, вакансію, компанію і файл резюме. Тому звідси беремо подачі й версію
 * резюме, а відповідь на «переглянуто чи ні» лишається питанням до Djinni.
 *
 * Зате ім'я файлу резюме — саме те поле, за яким воронка вміє порівнювати
 * версії між собою. На Djinni його немає взагалі.
 *
 * Розмітку встановлено за скріншотом 08.10.2026: рядок починається вузлом із
 * датою «ДД.ММ.РРРР ГГ:ХХ», далі посилання на вакансію, « в » і компанія,
 * нижче — «Резюме: <файл>.pdf».
 */
(function () {
  "use strict";

  var API = "__API__", TOKEN = "__TOKEN__";
  var DATE = /^\s*(\d{2})\.(\d{2})\.(\d{4})(?:\s+\d{2}:\d{2})?\s*$/;

  function text(el) { return el ? (el.textContent || "").replace(/\s+/g, " ").trim() : ""; }

  /* Вузол дати — найнадійніший якір: він унікальний за формою і стоїть
     на початку кожного запису. Шукати за класами тут ризиковано — саме так
     два попередні здогади про розмітку Djinni виявились хибними. */
  function dateNodes() {
    var out = [], walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    while (walker.nextNode()) {
      var el = walker.currentNode;
      if (el.children.length) continue;            // лише листові вузли
      if (DATE.test(el.textContent || "")) out.push(el);
    }
    return out;
  }

  function rowFor(node) {
    // Піднімаємось, доки контейнер не почне містити і дату, і посилання
    // на вакансію — тобто стане повним записом.
    var el = node, up = 0;
    while (el.parentElement && up < 6) {
      el = el.parentElement; up++;
      if (el.querySelector('a[href*="/vacancies/"], a[href*="/companies/"]')) return el;
    }
    return null;
  }

  function collect() {
    var rows = [], seen = {}, skipped = 0;
    var nodes = dateNodes();

    for (var i = 0; i < nodes.length; i++) {
      var m = (nodes[i].textContent || "").match(DATE);
      var iso = m[3] + "-" + m[2] + "-" + m[1];
      var box = rowFor(nodes[i]);
      if (!box) { skipped++; continue; }

      var link = box.querySelector('a[href*="/vacancies/"]');
      var position = text(link);
      if (!position) { skipped++; continue; }

      var blob = text(box);
      // «Позиція в Компанія» — компанія стоїть після окремого слова « в ».
      var company = "";
      var cm = blob.match(/\sв\s+([^·|]+?)(?:\s*▶|\s*Cover|\s*Резюме|$)/);
      if (cm) company = cm[1].trim();
      if (!company) {
        var cl = box.querySelector('a[href*="/companies/"]');
        company = text(cl);
      }

      // Ім'я файлу резюме = версія, якою подавались.
      var cv = "";
      var pdf = box.querySelector('a[href$=".pdf"], a[href*=".pdf"]');
      if (pdf) cv = text(pdf).replace(/\.pdf$/i, "");
      else {
        var fm = blob.match(/Резюме:\s*([^\s]+\.pdf)/i);
        if (fm) cv = fm[1].replace(/\.pdf$/i, "");
      }

      var url = link ? link.href : null;
      if (url && seen[url]) continue;
      if (url) seen[url] = true;

      rows.push({
        url: url, company: company || "—", position: position,
        applied_on: iso, status: null, status_on: null,
        note: /cover letter/i.test(blob) ? "із супровідним листом" : null,
        cv_version: cv || null
      });
    }
    return { rows: rows, skipped: skipped };
  }

  function send(rows, dry) {
    return fetch(API + "/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Sync-Token": TOKEN },
      body: JSON.stringify({ source: "dou", items: rows, dry_run: dry })
    }).then(function (r) { return r.json(); });
  }

  var found = collect();
  if (!found.rows.length) {
    alert("jobtrack: записів не знайдено.\n\nПереконайтесь, що відкрита вкладка\n" +
          "«Відгуки на вакансії» у вашому профілі DOU.");
    return;
  }

  send(found.rows, true).then(function (report) {
    var msg = "jobtrack — попередній перегляд (нічого ще не записано)\n\n" +
      "Знайдено подач: " + report.received +
      (found.skipped ? " (пропущено нерозібраних: " + found.skipped + ")" : "") + "\n" +
      "Буде створено нових: " + report.created + "\n" +
      "Зіставлено з наявними: " + report.matched + "\n\n";
    for (var i = 0; i < Math.min(found.rows.length, 14); i++) {
      var r = found.rows[i];
      msg += "• " + r.applied_on + "  " + r.company + " — " + r.position +
             (r.cv_version ? "  [" + r.cv_version + "]" : "  [резюме не визначено]") + "\n";
    }
    if (found.rows.length > 14) msg += "… ще " + (found.rows.length - 14) + "\n";
    msg += "\nЗаписати?";

    if (!confirm(msg)) return;
    send(found.rows, false).then(function (done) {
      alert("Записано: " + done.created + " нових подач.\n\n" +
            "DOU не показує, чи переглянули відгук — тому статусів тут немає.\n" +
            "Відповідь на це питання дає лише Djinni.");
    });
  }).catch(function (e) {
    alert("jobtrack: не вдалося звернутися до " + API + "\n" + e);
  });
})();
