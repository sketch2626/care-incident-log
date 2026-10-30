/* Mary's skills, the page half (docs/skills-design.md sections 3 and 10).
   window.MarySkills = {
     register(name, handlers)   a skill's screen.js calls this: handlers = {enter(el, opts), leave(el), effect(kind, data)}
                                plus aside:true to stand side by side with Mary: she slides left, the box is the right 60%
     apply(effect)              one effect from the server: settings, show_screen, leave_screen or a skill's own
     call(name, args)           POST /api/mary/skills/call ("<skill>__<action>"); applies its effects; resolves with the result
     handleLiveToolCall(tc, heard)  Live mode: runs each functionCall, resolves with a toolResponse {functionResponses: [...]}
     list()                     the skills the server listed
     isSkillScreen(name)        true when name is a skill's screen
   Every skill handler runs in try/catch; a throw tells the server (POST /api/mary/skills/<name>/broken). */
(function () {
  'use strict';
  var D = document;
  var skills = [];        // from GET /api/mary/skills
  var handlers = {};      // name -> handlers
  var boxes = {};         // name -> the screen's container element
  var screenNames = {};
  var broke = {};

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
    back.textContent = 'Back';
    back.addEventListener('click', function () { if (app()) { app().show('everyday'); } });
    var body = D.createElement('div');
    body.className = 'skill-body';
    el.appendChild(body);
    el.appendChild(back);
    var scr = D.getElementById('scr') || D.body;
    scr.appendChild(el);
    boxes[name] = el;
    return el;
  }

  function register(name, h) {
    handlers[name] = h || {};
    if (!screenNames[name] && app() && app().registerScreen) {
      screenNames[name] = true;
      app().registerScreen(name, {
        enter: function (opts) {
          var el = boxFor(name);
          el.classList.toggle('aside', !!handlers[name].aside);
          if (handlers[name].aside && app() && app().sideBySide) { app().sideBySide(true); }
          el.hidden = false;
          guard(name, function () { if (handlers[name].enter) { handlers[name].enter(el.firstChild, opts || {}); } });
        },
        leave: function () {
          var el = boxFor(name);
          guard(name, function () { if (handlers[name].leave) { handlers[name].leave(el.firstChild); } });
          el.hidden = true;
          if (handlers[name].aside && app() && app().sideBySide) { app().sideBySide(false); }
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
        return;
      }
      if (kind === 'show_screen') {
        if (a && data.screen && !(a.currentScreen && a.currentScreen() === 'emergency')) { a.show(data.screen); }  // M4a: never cover the emergency screen
        return;
      }
      if (kind === 'leave_screen') {
        if (a && a.currentScreen && a.currentScreen() === data.screen) { a.show('everyday'); }
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
    isSkillScreen: function (name) { return !!screenNames[name]; }
  };

  if (D.readyState === 'loading') { D.addEventListener('DOMContentLoaded', load); } else { load(); }
})();
