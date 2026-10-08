// ==UserScript==
// @name         jobtrack — автоматичний збір статусів Djinni
// @namespace    jobtrack
// @version      1.0
// @description  Періодично читає сторінку відгуків у ВАШІЙ сесії й надсилає статуси в локальний журнал. Нічого не зберігає, нікуди не логіниться.
// @match        https://djinni.co/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

/* Чому саме так, а не робот із збереженим логіном.
 *
 * Автоматичне відстеження «зі свого боку» означало б тримати чужі облікові
 * дані або куки — тобто ризикувати акаунтом, який є єдиним каналом пошуку.
 * Тут натомість працює ВАШ браузер у ВАШІЙ сесії: скрипт робить рівно те,
 * що ви робили б руками, і нічого не обходить.
 *
 * Ціна рішення названа чесно: потрібна відкрита вкладка Djinni. Будь-яка —
 * сторінку відгуків скрипт дістає сам запитом із того ж походження.
 */
(function () {
  "use strict";

  var API = "__API__", TOKEN = "__TOKEN__";
  var EVERY_MIN = 20;           // ввічливий темп: три запити на годину
  var KEY = "jobtrack:last-sync";

  // Та сама логіка розбору, що й у ручному збирачі. Тримається тут копією
  // свідомо: userscript має бути самодостатнім файлом, який користувач
  // встановлює один раз і який не ламається від змін на нашому боці.
  var AUTO = /це автоматична відповідь|автоматичн\w* відповід|automatic reply|auto-?reply|передали (його )?на розгляд/i;

  function text(el) { return el ? (el.textContent || "").replace(/\s+/g, " ").trim() : ""; }

  function statusFrom(blob) {
    if (AUTO.test(blob)) return "auto_reply";
    if (/не\s+перегл|не\s+прочит|unread/i.test(blob)) return null;
    if (/ваш відгук на цю позицію відхилено|відхилено|відмовл/i.test(blob)) return "rejected";
    if (/призупиня|призупинил|пауз|вакансію закрит|позицію закрит/i.test(blob)) return "rejected";
    if (/запрош|співбес|interview|созвон|дзвінок|calendly/i.test(blob)) return "invited";
    if (/тестов|test task|тестове завдання/i.test(blob)) return "test_task";
    if (/офер|offer|пропозиці[юї] роботи/i.test(blob)) return "offer";
    if (/ви відгукнулись/i.test(blob) && !/\bВи:/.test(blob)) return null;
    if (/дякую|вітаю|на жаль|доброго дня|добрий день|hello|hi\b/i.test(blob)) return "viewed";
    return null;
  }

  var MONTHS = ["січ", "лют", "берез", "квіт", "трав", "черв",
                "лип", "серп", "верес", "жовт", "листоп", "груд"];
  function dateFrom(box) {
    var rel = text(box).match(/\b(\d+)\s*(mo|d|h|w|y)\b/);
    if (rel) {
      var n = parseInt(rel[1], 10), d = new Date();
      if (rel[2] === "mo") d.setMonth(d.getMonth() - n);
      else if (rel[2] === "d") d.setDate(d.getDate() - n);
      else if (rel[2] === "w") d.setDate(d.getDate() - n * 7);
      else if (rel[2] === "y") d.setFullYear(d.getFullYear() - n);
      return d.toISOString().slice(0, 10);
    }
    var t = box.querySelector("time[datetime]");
    if (t) { var s = t.getAttribute("datetime").slice(0, 10); if (/^\d{4}-\d\d-\d\d$/.test(s)) return s; }
    return null;
  }

  function rowsIn(root) {
    var out = [];
    var boxes = root.querySelectorAll(".proposal, .js-proposal");
    for (var i = 0; i < boxes.length; i++) {
      var box = boxes[i], id = box.getAttribute("data-id") || "";
      if (!id) continue;
      var link = box.querySelector('a[href*="/jobs/company-"]');
      var companyEl = link ? (link.querySelector("span") || link) : null;
      var posEl = box.querySelector('.job_title a, a[href^="/my/inbox/"]:not(.proposal-absolute-link)');
      var blob = text(box), when = dateFrom(box), st = statusFrom(blob);
      out.push({
        url: "https://djinni.co/my/inbox/" + id + "/",
        company: (text(companyEl).split("·")[0].trim()) || "—",
        position: text(posEl) || "—",
        applied_on: when,
        status: st,
        status_on: st ? when : null,
        note: st === "auto_reply" ? "автовідповідь — перегляд НЕ підтверджено" : null
      });
    }
    return out;
  }

  function bucket(name) {
    var url = name ? "/my/inbox?bucket=" + name : "/my/inbox";
    return fetch(url, { credentials: "include" })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        return rowsIn(new DOMParser().parseFromString(html, "text/html"));
      })
      .catch(function () { return []; });
  }

  function sync() {
    return Promise.all([bucket(""), bucket("archive")]).then(function (parts) {
      var rows = [], seen = {};
      parts.forEach(function (p) {
        p.forEach(function (r) { if (!seen[r.url]) { seen[r.url] = true; rows.push(r); } });
      });
      if (!rows.length) return;                       // не залогінені або інша розмітка

      return fetch(API + "/api/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Sync-Token": TOKEN },
        body: JSON.stringify({ source: "djinni", items: rows, dry_run: false })
      }).then(function (r) { return r.json(); }).then(function (rep) {
        try { localStorage.setItem(KEY, String(Date.now())); } catch (e) {}
        if (rep.created || rep.events_added) {
          console.log("[jobtrack] синхронізовано: +" + rep.created + " подач, +" +
                      rep.events_added + " подій із " + rep.received + " рядків");
        }
      });
    }).catch(function (e) {
      // Локальний сервіс може бути не піднятий — це нормальний стан, не помилка.
      console.debug("[jobtrack] журнал недоступний:", e && e.message);
    });
  }

  function due() {
    try {
      var last = parseInt(localStorage.getItem(KEY) || "0", 10);
      return Date.now() - last > EVERY_MIN * 60 * 1000;
    } catch (e) { return true; }
  }

  // Перший прогін — із затримкою, щоб не змагатися з завантаженням сторінки.
  setTimeout(function () { if (due()) sync(); }, 8000);
  setInterval(function () { if (due()) sync(); }, EVERY_MIN * 60 * 1000);
})();
