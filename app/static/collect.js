/* Читач сторінки «Мої відгуки» у ВЛАСНІЙ сесії користувача.
 *
 * Межа, через яку цей файл узагалі існує: сторінка за логіном, і автоматизувати
 * вхід означало б тримати чужі облікові дані. Тут натомість людина сама відкриває
 * сторінку, а скрипт лише читає те, що вже на екрані.
 *
 * Селектори НЕ перевірені — сторінка за логіном, автор коду її не бачив. Тому
 * спершу показується попередній перегляд, і лише після підтвердження дані йдуть
 * у журнал. Незнайомі написання статусів виводяться окремо: перший прогін — це
 * розвідка розмітки, а не імпорт.
 */
(function () {
  "use strict";

  var API = "__API__", TOKEN = "__TOKEN__", SOURCE = "__SOURCE__";

  // Слова → наші стани. Регістр і закінчення не враховуються: шукаємо корінь.
  var STATUS_WORDS = [
    [/відхил|відмов|reject|declin|не підійш/i, "rejected"],
    [/запрош|invit|співбес|interview|intervi/i, "invited"],
    [/тестов|test task|завдання/i, "test_task"],
    [/офер|offer|пропозиц/i, "offer"],
    [/перегл|переглян|viewed|seen|прочит/i, "viewed"],
    [/не перегл|unread|не прочит/i, null]   // явна відсутність перегляду
  ];

  function statusFrom(text) {
    if (!text) return undefined;
    // «не переглянуто» мусить перевірятись ПЕРЕД «переглянуто», інакше
    // підрядок збігається і дає протилежний результат.
    if (/не\s+перегл|unread|не\s+прочит/i.test(text)) return null;
    for (var i = 0; i < STATUS_WORDS.length; i++) {
      if (STATUS_WORDS[i][0].test(text)) return STATUS_WORDS[i][1];
    }
    return undefined;   // невідоме написання — повідомити, не вгадувати
  }

  function text(el) { return el ? (el.textContent || "").replace(/\s+/g, " ").trim() : ""; }

  function collect() {
    var rows = [], unknown = [], seen = {};

    // Беремо кожне посилання на вакансію і піднімаємось до контейнера рядка.
    var links = document.querySelectorAll('a[href*="/jobs/"], a[href*="/vacancies/"]');
    for (var i = 0; i < links.length; i++) {
      var a = links[i];
      var href = a.href;
      if (!href || seen[href]) continue;

      var box = a.closest("li, tr, article, .card, .list-item") || a.parentElement;
      if (!box) continue;
      var blob = text(box);
      if (!blob) continue;

      seen[href] = true;

      var st = statusFrom(blob);
      if (st === undefined && blob.length < 400) unknown.push(blob.slice(0, 120));

      rows.push({
        url: href,
        position: text(a) || "—",
        company: companyNear(box, a) || "—",
        status: st === undefined ? null : st,
        note: null
      });
    }
    return { rows: rows, unknown: unknown };
  }

  function companyNear(box, link) {
    // Назва компанії зазвичай поруч: окреме посилання на профіль компанії
    // або сусідній рядок. Беремо перше, що не є самим посиланням на вакансію.
    var cand = box.querySelector('a[href*="/company"], a[href*="/companies/"], .company, .text-muted');
    if (cand && cand !== link) { var t = text(cand); if (t) return t; }
    var parts = text(box).split("·");
    return parts.length > 1 ? parts[1].trim() : "";
  }

  function send(rows, dry) {
    return fetch(API + "/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Sync-Token": TOKEN },
      body: JSON.stringify({ source: SOURCE, items: rows, dry_run: dry })
    }).then(function (r) { return r.json(); });
  }

  var found = collect();
  if (!found.rows.length) {
    alert("jobtrack: на сторінці не знайдено жодного рядка з посиланням на вакансію.\n\n" +
          "Найімовірніше, розмітка інша, ніж очікувалось. Надішліть автору\n" +
          "приклад HTML одного рядка — селектори буде уточнено.");
    return;
  }

  send(found.rows, true).then(function (report) {
    var msg = "jobtrack — попередній перегляд (нічого ще не записано)\n\n" +
      "Прочитано рядків: " + report.received + "\n" +
      "Буде створено нових: " + report.created + "\n" +
      "Зіставлено з наявними: " + report.matched + "\n" +
      "Буде додано подій: " + report.events_added + "\n";
    if (report.ambiguous.length)
      msg += "\nНеоднозначні (можливий дубль у журналі): " + report.ambiguous.join(", ") + "\n";
    if (found.unknown.length)
      msg += "\nНезнайомі написання статусу (" + found.unknown.length + "): \n  " +
             found.unknown.slice(0, 5).join("\n  ") + "\n";
    msg += "\nЗаписати?";

    if (!confirm(msg)) return;
    send(found.rows, false).then(function (done) {
      alert("Записано: " + done.created + " нових, " + done.events_added + " подій.");
    });
  }).catch(function (e) {
    alert("jobtrack: не вдалося звернутися до " + API + "\n" + e +
          "\n\nПеревірте, що стек піднято: docker compose up -d");
  });
})();
