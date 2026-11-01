/* Mary's skills, the page half (docs/skills-design.md sections 3 and 10).
   window.MarySkills = {
     register(name, handlers)   a skill's screen.js calls this: handlers = {enter(el, opts), leave(el), effect(kind, data)}
                                plus aside:true to stand side by side with Mary: she slides left, the box is the right 60%
     apply(effect)              one effect from the server: settings, show_screen, leave_screen or a skill's own
     call(name, args)           POST /api/mary/skills/call ("<skill>__<action>"); applies its effects; resolves with the result
     handleLiveToolCall(tc, heard)  Live mode: runs each functionCall, resolves with a toolResponse {functionResponses: [...]}
     list()                     the skills the server listed
     isSkillScreen(name)        true when name is a skill's screen
     comingBack()               M13b: the skill set aside that comes back when this screen closes, or null
     backLabel()                M13b: that skill's menu label in lower case ("word search"), or null
   M13b: one thing beside Mary at a time. A game's handlers say setAside:true: when another skill's screen takes its place
   its page is hidden just as it is (not ended), Mary stays side by side, and it comes back where they left off when that
   screen closes. A screen's optional backChanged() hears that the skill behind it was ended, so its Back goes elsewhere.
   Every skill handler runs in try/catch; a throw tells the server (POST /api/mary/skills/<name>/broken). */
(function () {
  'use strict';
  var D = document;
  var skills = [];        // from GET /api/mary/skills
  var handlers = {};      // name -> handlers
  var boxes = {};         // name -> the screen's container element
  var screenNames = {};
  var broke = {};
  var setAside = [];      // M13b: names of skills set aside, last on top; their pages wait hidden, just as they were

  function log(e) { try { console.log('[skills]', e); } catch (x) { /* nothing */ } }
  function app() { return window.MaryApp; }

  function tell(url, method, body) {
    var init = { method: method, cache: 'no-store', headers: { 'X-Tracker': '1', 'Content-Type': 'application/json' } };
    if (method !== 'GET') { init.body = JSON.stringify(body || {}); }
    return fetch(url, init).then(function (r) { return r.json(); });
  }

  function broken(name) {
    if (broke[name]) { return; }
    broke[name] = true;
    try { tell('/api/mary/skills/' + encodeURIComponent(name) + '/broken', 'POST', {}).catch(log); } catch (e) { log(e); }
  }

  // Runs one handler of one skill; a throw marks the skill broken and gives undefined.
  function guard(name, fn) {
    try { return fn(); } catch (e) { log(e); broken(name); return undefined; }
  }

  // M17: Mary's own words for the way back ("Back to Mary" or "Back to Sam"); app.js keeps them current
  function backWords() {
    try {
      var l = D.querySelector('.backLbl');
      if (l && l.textContent) { return l.textContent; }
    } catch (e) { /* nothing */ }
    return 'Back';
  }

  function boxFor(name) {
    if (boxes[name]) { return boxes[name]; }
    var el = D.createElement('div');
    el.className = 'skill-screen';
    el.setAttribute('data-skill', name);
    el.hidden = true;
    el.style.cssText = 'position:absolute;left:0;right:0;top:0;bottom:0;overflow:auto;z-index:5;padding:16px;' +
      'box-sizing:border-box;font-size:22px';
    var back = D.createElement('button');
    back.type = 'button';
    back.className = 'btn';
    back.textContent = backWords();   // M17: says where it goes
    back.addEventListener('click', function () { if (app()) { app().show('everyday'); } });
    var body = D.createElement('div');
    body.className = 'skill-body';
    el.appendChild(back);   // M17: first, so it can stay at the top
    el.appendChild(body);
    var scr = D.getElementById('scr') || D.body;
    scr.appendChild(el);
    boxes[name] = el;
    return el;
  }

  // M13b: true when name is a skill's screen that stands side by side with Mary
  function isAsideScreen(name) { return !!(screenNames[name] && handlers[name] && handlers[name].aside); }

  function comingBack() { return setAside.length ? setAside[setAside.length - 1] : null; }

  // M13b: what the Back button calls the skill that comes back
  function backLabel() {
    var top = comingBack();
    for (var i = 0; top && i < skills.length; i++) {
      if (skills[i].name === top) { return (skills[i].menu && skills[i].menu.label) ? String(skills[i].menu.label).toLowerCase() : null; }
    }
    return null;
  }

  // M13b: ends a skill that was set aside, for real: it won't come back
  function endAside(name) {
    var i = setAside.indexOf(name);
    if (i >= 0) { setAside.splice(i, 1); }
    var el = boxFor(name);
    guard(name, function () { if (handlers[name].leave) { handlers[name].leave(el.firstChild); } });
    el.hidden = true;
  }

  // M13b: a skill ended or switched off while hidden: it won't come back, and what's on top hears where Back goes now
  function dropAside(name) {
    if (setAside.indexOf(name) < 0) { return; }
    endAside(name);
    var a = app(), onTop = a && a.currentScreen && a.currentScreen();
    if (onTop && handlers[onTop] && handlers[onTop].backChanged) { guard(onTop, function () { handlers[onTop].backChanged(); }); }
  }

  function register(name, h) {
    handlers[name] = h || {};
    if (!screenNames[name] && app() && app().registerScreen) {
      screenNames[name] = true;
      app().registerScreen(name, {
        enter: function (opts) {
          var el = boxFor(name);
          var waiting = setAside.indexOf(name);   // M13b
          if (waiting >= 0) {   // M13b: back where they left off: its page was only hidden, so nothing is redrawn
            setAside.splice(waiting, 1);
            if (handlers[name].aside && app() && app().sideBySide) { app().sideBySide(true); }
            el.hidden = false;
            return;
          }
          el.classList.toggle('aside', !!handlers[name].aside);
          if (handlers[name].aside && app() && app().sideBySide) { app().sideBySide(true); }
          el.hidden = false;
          guard(name, function () { if (handlers[name].enter) { handlers[name].enter(el.firstChild, opts || {}); } });
        },
        leave: function (next) {
          var el = boxFor(name);
          if (handlers[name].setAside && next !== name && screenNames[next] && setAside.indexOf(next) < 0) {   // M13b: set aside, not ended; Mary stays put; not when the one waiting comes back, so two games never swap forever
            if (setAside.indexOf(name) < 0) { setAside.push(name); }
            el.hidden = true;
            return;
          }
          guard(name, function () { if (handlers[name].leave) { handlers[name].leave(el.firstChild); } });
          el.hidden = true;
          // M13b: emergency and the like: nothing waits behind them
          if (!screenNames[next] && next !== 'everyday') { setAside.slice().forEach(function (n) { endAside(n); }); }
          // M13b: not when the next screen stands beside her too, so she doesn't slide out and back
          if (handlers[name].aside && !isAsideScreen(next) && app() && app().sideBySide) { app().sideBySide(false); }
        }
      });
    }
  }

  function apply(effect) {
    if (!effect || typeof effect !== 'object') { return; }
    var kind = effect.kind, data = effect.data || {};
    var a = app();
    try {
      if (kind === 'settings') {
        if (a && a.applySettings && data.values) { a.applySettings(data.values); }
        Object.keys(data.skills || {}).forEach(function (n) { if (data.skills[n] === false) { dropAside(n); } });   // M13b: switched off while hidden
        return;
      }
      if (kind === 'show_screen') {
        if (a && data.screen && !(a.currentScreen && a.currentScreen() === 'emergency')) { a.show(data.screen); }  // M4a: never cover the emergency screen
        return;
      }
      if (kind === 'leave_screen') {
        if (a && a.currentScreen && a.currentScreen() === data.screen) { a.show('everyday'); }
        else { dropAside(data.screen); }   // M13b: a game ended while hidden must not come back
        return;
      }
      if (kind === 'book_ask' || kind === 'book_out') {   // M19 piece 6b: her forget, on the address book's screens
        if (a && a.bookEffect) { a.bookEffect(kind, data); }
        return;
      }
      var name = effect.skill;
      if (name && handlers[name] && handlers[name].effect) {
        guard(name, function () { handlers[name].effect(kind, data); });
      }
    } catch (e) { log(e); }
  }

  function call(name, args, heard) {
    var body = { name: name, args: args || {} };
    if (heard) { body.heard = String(heard); }  // M4a: the server refuses tools on an emergency line
    var a = app(), at = a && a.currentScreen ? a.currentScreen() : null;   // M13b
    if (at && screenNames[at]) { body.screen = at; }   // M13b
    if (comingBack()) { body.aside = comingBack(); }   // M13b: a call without it clears the server's note
    return tell('/api/mary/skills/call', 'POST', body).then(function (res) {
      var effects = (res && res.effects) || [];
      for (var i = 0; i < effects.length; i++) { apply(effects[i]); }
      return res;
    });
  }

  function handleLiveToolCall(tc, heard) {  // M4a: heard = what the resident just said, for the emergency gate
    var calls = (tc && (tc.functionCalls || tc.function_calls)) || [];
    var out = [];
    var chain = Promise.resolve();
    calls.forEach(function (fc) {
      chain = chain.then(function () {
        return call(fc.name, fc.args, heard).then(function (res) {
          out.push({ id: fc.id, name: fc.name, response: (res && res.response) || { error: 'no_answer' } });
        }, function () {
          out.push({ id: fc.id, name: fc.name, response: { error: 'not_working' } });
        });
      });
    });
    return chain.then(function () { return { functionResponses: out }; });
  }

  // M4b: a switched-on skill with a screen is listed in "Things Mary can do" (the old menu buttons are gone)
  function addMenuButton(s) {
    if (!app() || typeof app().addThing !== 'function') { return; }
    app().addThing({
      name: s.name,
      label: s.menu.label,
      say: s.menu.say || '',
      open: function () { if (app()) { app().show(s.name); } }
    });
  }

  function addFile(tag, attrs) {
    var el = D.createElement(tag);
    for (var k in attrs) { if (attrs.hasOwnProperty(k)) { el[k] = attrs[k]; } }
    D.head.appendChild(el);
  }

  function load() {
    return tell('/api/mary/skills', 'GET').then(function (res) {
      skills = (res && res.skills) || [];
      skills.forEach(function (s) {
        if (!s.on) { return; }
        if (s.style) { addFile('link', { rel: 'stylesheet', href: s.style }); }
        if (s.script) { addFile('script', { src: s.script, onerror: function () { broken(s.name); } }); }
        if (s.menu && s.menu.label && s.script) { addMenuButton(s); }
      });
    }).catch(log);
  }

  window.MarySkills = {
    register: register,
    apply: apply,
    call: call,
    handleLiveToolCall: handleLiveToolCall,
    list: function () { return skills.slice(); },
    isSkillScreen: function (name) { return !!screenNames[name]; },
    comingBack: comingBack,   // M13b
    backLabel: backLabel      // M13b
  };

  if (D.readyState === 'loading') { D.addEventListener('DOMContentLoaded', load); } else { load(); }
})();
