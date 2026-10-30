from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M4a: Live's stories and goodbyes, and the one voice of a Normal or Offline talk (web/mary/app.js), checked with
Node. app.js needs a page to run, so the helper blocks are cut out of it and the rest of the page is stubbed."""
import json
import os
import shutil
import subprocess
import unittest

import mary

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "mary", "app.js")
TALKLIVE = os.path.join(ROOT, "web", "mary", "talklive.js")
VOICEOUT = os.path.join(ROOT, "web", "mary", "voiceout.js")

# The same strings go through mary.not_english and the page's notEnglish, so the two rules can't drift apart.
SCRIPTS = ["Good night Mary", "", "12345 !?", "Café au lait, s'il vous plaît", "你好世界", "こんにちは、元気ですか",
           "Привет как дела", "नमस्ते दुनिया", "مرحبا بالعالم", "Hello 你好", "ok 你好世界再见", "🙂🙂 ok",
           "“Yes,” she said — fine…"]

CHECKS = r"""
const assert = require('assert');
function words(n, seed) { return Array.from({ length: n }, function (_, i) { return (seed || 'word') + i; }).join(' '); }
function sentences(count, size) {
  return Array.from({ length: count }, function (_, i) { return words(size - 1, 's' + i + 'w') + ' end.'; }).join(' ');
}
function count(t) { return t.split(/\s+/).length; }

// paragraphs stay whole, and the newlines don't get flattened first
const a = sentences(3, 10), b = sentences(4, 10), c = sentences(2, 15);
assert.deepStrictEqual(storyParts(a + '\n\n' + b + '\n\n' + c), [a, b, c]);
assert.deepStrictEqual(storyParts(a + '\r\n\r\n' + b), [a, b]);
assert.deepStrictEqual(storyParts(a + '\n  \n' + b), [a, b]);

// a long paragraph is cut at sentence ends, and nothing is lost
const long = sentences(15, 10);
let p = storyParts(long + '\n\n' + a);
assert.ok(p.length >= 3, 'cut: ' + p.length);
p.forEach(function (x) { assert.ok(count(x) <= 90, count(x)); assert.ok(/end\.$/.test(x), x.slice(-20)); });
assert.strictEqual(p.join(' '), long + ' ' + a);

// no blank lines: about every 70 words, at sentence ends
const flat = sentences(28, 10);
p = storyParts(flat);
assert.strictEqual(p.length, 4);
p.forEach(function (x) { assert.strictEqual(count(x), 70); });
assert.strictEqual(p.join(' '), flat);

// a tiny part joins the next one; a tiny last part joins the one before
const title = 'The Bear And The Bee.';
assert.deepStrictEqual(storyParts(title + '\n\n' + a), [title + ' ' + a]);
assert.deepStrictEqual(storyParts(a + '\n\n' + title), [a + ' ' + title]);
assert.deepStrictEqual(storyParts(title + '\n\n' + title), [title + ' ' + title]);

// at most 6 parts, in order, with nothing lost
const many = Array.from({ length: 10 }, function (_, i) { return words(39, 'p' + i) + ' end.'; });
p = storyParts(many.join('\n\n'));
assert.strictEqual(p.length, 6);
assert.strictEqual(p.join(' '), many.join(' '));
assert.ok(Math.max.apply(null, p.map(count)) <= 80);
const huge = sentences(100, 10);
p = storyParts(huge);
assert.strictEqual(p.length, 6);
assert.strictEqual(p.join(' '), huge);

// edges
assert.deepStrictEqual(storyParts('   \n\n  '), []);
assert.deepStrictEqual(storyParts(null), []);
assert.deepStrictEqual(storyParts('A short tale.'), ['A short tale.']);
const one = words(120);                                  // one long sentence has nowhere to cut
assert.deepStrictEqual(storyParts(one), [one]);
assert.deepStrictEqual(storyParts('Mr. Smith  went *home*. He slept.'), ['Mr. Smith went home. He slept.']);

// the answer Live gets, and the story moving on
const st = { parts: ['one', 'two'], next: 0, paused: true };
let r = storyStep(st);
assert.strictEqual(r.part, 'one');
assert.strictEqual(r.more, true);
assert.ok(/exactly as written/.test(r.note) && /comes by itself/.test(r.note));
assert.strictEqual(st.paused, false);
r = storyStep(st);
assert.strictEqual(r.part, 'two');
assert.strictEqual(r.more, false);
assert.deepStrictEqual(Object.keys(storyStep(st)).sort(), ['done', 'note']);
assert.strictEqual(storyStep(null).done, true);
assert.ok(storyNextLine('PART', false).endsWith('add nothing after it: PART)'));
assert.ok(/It is the end of the story, so stop after its last line: PART\)$/.test(storyNextLine('PART', true)));

// what they've said since their last pause
const hs = { text: '', mark: 0, at: 0 };
assert.strictEqual(heardTail(hs, 'my dinner was', 1000), 'my dinner was');
assert.strictEqual(heardTail(hs, 'my dinner was cold', 1500), 'my dinner was cold');   // the same breath
assert.strictEqual(heardTail(hs, 'my dinner was cold go to sleep', 3000), 'go to sleep');   // after a pause
assert.strictEqual(heardTail(hs, 'my dinner was cold go to sleep now', 3300), 'go to sleep now');
assert.strictEqual(heardFinal(hs, 'my dinner was cold go to sleep now'), 'go to sleep now');
assert.strictEqual(heardFinal(hs, 'a typed line'), 'a typed line');
assert.strictEqual(heardFinal(null, 'a typed line'), 'a typed line');
assert.strictEqual(heardTail(hs, 'bye', 3400), 'bye');                                 // shorter: a new turn
const longer = 'I said something longer than bye';
assert.strictEqual(heardTail(hs, longer, 9000), longer);                               // longer, but not the same text
assert.strictEqual(heardTail(hs, longer, 12000), longer);                              // no new words: no new start

// the same rule as mary.not_english
CASES.forEach(function (x) { assert.strictEqual(notEnglish(x[0]), x[1], x[0]); });
assert.strictEqual(notEnglish(null), false);

// the talk's one voice
const all = ['live', 'normal', 'offline'];
assert.strictEqual(micMissGoesOn(0), true);
assert.strictEqual(micMissGoesOn(1), false);
assert.strictEqual(talkVoice('normal', false, all), 'normal');
assert.strictEqual(talkVoice('normal', true, all), 'offline');
assert.strictEqual(talkVoice('normal', true, ['normal', 'offline']), 'offline');
assert.strictEqual(talkVoice('normal', true, ['normal']), '');         // the computer's own voice: no Kokoro here
assert.strictEqual(talkVoice('offline', false, ['offline']), 'offline');
assert.strictEqual(talkVoice('offline', true, ['offline']), 'offline');
assert.strictEqual(talkVoice('live', false, all), 'offline');          // Gemini TTS is only for Normal
assert.strictEqual(talkVoice('live', false, ['live', 'normal']), '');
assert.strictEqual(talkVoice('', false, []), '');

// moving on goes forward only, so a talk can't flip back
assert.strictEqual(voiceAfter(all, 'normal'), 'offline');
assert.strictEqual(voiceAfter(all, 'offline'), '');
assert.strictEqual(voiceAfter(['normal', 'offline'], 'normal'), 'offline');
assert.strictEqual(voiceAfter(['normal', 'offline'], 'offline'), '');
assert.strictEqual(voiceAfter(['offline'], 'offline'), '');
console.log('OK story helpers');
"""

BYE_CHECKS = r"""
const assert = require('assert');
["Go to sleep", "Okay Mary, you can go to sleep now.", "You can rest now", "That's all for now", "that'll be all for today",
 "Go on to sleep, Mary", "good night", "Goodbye", "Bye now", "Take a nap", "I'm going to sleep"].forEach(function (t) {
  assert.strictEqual(isGoodbye(t), true, t);
});
// a complaint or a question about sleep is not a goodbye, and she keeps listening
["I can't get to sleep", "I can't go to sleep", "I couldn't get to sleep last night", "I need some rest",
 "I want to go to sleep but my chest hurts", "Why did she go to sleep?", "I don't want to say goodbye",
 "That's all I can take", "That's enough", "They told me to go to sleep",
 "she told the kids to go to sleep and then the bear came", "", "hello"].forEach(function (t) {
  assert.strictEqual(isGoodbye(t), false, t);
});
console.log('OK goodbye');
"""

# The rest of the page, for the Live block. Timers are run by hand.
LIVE_STUBS = r"""
const assert = require('assert');
var timers = new Map(), timerId = 0, clock = 1000;
Date.now = function () { return clock; };
function setTimeout(fn) { timers.set(++timerId, fn); return timerId; }
function clearTimeout(id) { timers.delete(id); }
function setInterval() { return 0; }
function clearInterval() {}
function tick() { var list = Array.from(timers.values()); timers.clear(); list.forEach(function (f) { f(); }); }
var S = { convo: null, screen: 'everyday', talkOrder: ['live', 'normal', 'offline'], talkMode: 'live', voiceMode: '' };
var Sp = { sess: null };
var MSG = { emergency: 'HELP WORDS' };
var LIVE_SAFETY = '(SAFETY ';
var greets = [], stops = 0, finished = 0, speaking = false, said = [];
var window = {
  MaryLive: { stopSpeaking: function () { stops++; } },
  MarySkills: { handleLiveToolCall: function (tc) {
    return Promise.resolve({ functionResponses: tc.functionCalls.map(function (fc) {
      return { id: fc.id, name: fc.name, response: fc.name === 'tell_story' ? { story: STORY } : { ok: true } };
    }) });
  } }
};
function greetLive(t) { greets.push(t); return true; }
function liveSpeaking() { return speaking; }
function finishLive() { finished++; S.convo = null; }
function liveBye() { return 'BYE LINE'; }
function liveByeCap(c) { finishLive(c); }
function setPhase() {}
function applyMood() {}
function restPhase() { return 'idle'; }
function log() {}
function show(n) { S.screen = n; }
function showCaption() {}
function capLiveEmergency() {}
function liveIdleCheck() {}
function say(t) { said.push(t); }
var STORY = [1, 2, 3, 4].map(function (n) {
  return 'Paragraph ' + n + ' has quite a few words in it and it runs on and on until it is long enough to stay a part by itself.';
}).join('\n\n');
function newTalk() {
  var c = { live: true, open: true, ending: false, story: null, heard: '', heardCheck: null, toolBusy: 0, byeDone: false,
    byeAudio: false, lastAct: 0 };
  S.convo = c;
  S.screen = 'everyday';
  greets = []; stops = 0; finished = 0; speaking = false; said = [];
  timers.clear();
  return c;
}
"""

LIVE_CHECKS = r"""
(async function () {
  // earlier words, a pause, then the goodbye: only the tail counts, and a later piece doesn't lose it
  let c = newTalk();
  const before = 'my dinner came late again and it was stone cold and nobody cared';
  assert.strictEqual(liveHeardPiece(c, before), false);
  assert.strictEqual(timers.size, 0);
  clock += 2000;
  liveHeardPiece(c, before + ' go to sleep');
  assert.strictEqual(timers.size, 1);
  clock += 300;
  liveHeardPiece(c, before + ' go to sleep Mary');
  assert.strictEqual(timers.size, 1);
  tick();
  assert.strictEqual(c.ending, true);
  assert.deepStrictEqual(greets, ['BYE LINE']);
  assert.strictEqual(stops, 1);
  assert.strictEqual(finished, 0);
  // the turn she was cut off from finishes first: that is not her goodbye
  liveTurnDone(c);
  assert.strictEqual(finished, 0);
  speaking = true;
  liveSpeakingChanged(c, true);
  assert.strictEqual(c.byeAudio, true);
  liveTurnDone(c);
  assert.strictEqual(finished, 0);      // still coming out of the speakers
  speaking = false;
  liveSpeakingChanged(c, false);
  assert.strictEqual(finished, 1);
  assert.deepStrictEqual(said, []);     // never a second voice

  // sound already drained when her turn ends
  c = newTalk();
  liveByeNow(c);
  speaking = true; liveSpeakingChanged(c, true);
  speaking = false; liveSpeakingChanged(c, false);
  assert.strictEqual(finished, 0);
  liveTurnDone(c);
  assert.strictEqual(finished, 1);

  // the goodbye that never comes: the cap closes the talk
  c = newTalk();
  liveByeNow(c);
  tick();
  assert.strictEqual(finished, 1);

  // the tail stops being a goodbye: the timer goes
  c = newTalk();
  liveHeardPiece(c, 'go to sleep');
  assert.strictEqual(timers.size, 1);
  liveHeardPiece(c, 'go to sleep is what the nurse told him to do');
  assert.strictEqual(timers.size, 0);
  assert.strictEqual(c.ending, false);

  // a goodbye over a story: the story holds at once, even while she is speaking, and the goodbye ends it
  c = newTalk();
  c.story = { parts: ['a', 'b'], next: 1, paused: false, sounded: true, askedAt: clock };
  speaking = true;
  liveHeardPiece(c, 'good night');
  assert.strictEqual(c.story.paused, true);
  assert.strictEqual(timers.size, 1);
  tick();
  assert.strictEqual(c.story, null);
  assert.deepStrictEqual(greets, ['BYE LINE']);

  // a garbled line is hidden, is no goodbye and no cut-in
  c = newTalk();
  c.story = { parts: ['a', 'b'], next: 1, paused: false, sounded: true, askedAt: clock };
  assert.strictEqual(liveHeardPiece(c, '你好世界'), true);
  assert.strictEqual(timers.size, 0);
  assert.strictEqual(c.story.paused, false);

  // the story: first part at once, then a part per finished turn
  c = newTalk();
  let r = await liveToolCall(c, { functionCalls: [{ id: '1', name: 'tell_story', args: {} }] });
  let a = r.functionResponses[0].response;
  assert.ok(a.part.startsWith('Paragraph 1'), a.part);
  assert.strictEqual(a.more, true);
  assert.ok(a.note && a.story === undefined);
  assert.strictEqual(c.toolBusy, 0);
  storyNext(c);                               // her lead-in finished, but the first part hasn't been heard
  assert.strictEqual(greets.length, 0);
  c.story.sounded = true;
  storyNext(c);
  assert.strictEqual(greets.length, 1);
  assert.ok(/Go on with the story/.test(greets[0]) && /Paragraph 2/.test(greets[0]) && !/end of the story/.test(greets[0]));

  // real words in the gap hold it; her own sound and small noises don't
  c.story.sounded = true;
  speaking = true;
  liveHeardPiece(c, 'her own words coming back');
  assert.strictEqual(c.story.paused, false);
  speaking = false;
  c.heardTrack = null;
  liveHeardPiece(c, 'okay');
  assert.strictEqual(c.story.paused, false);
  c.heardTrack = null;
  liveHeardPiece(c, 'wait, who was that?');
  assert.strictEqual(c.story.paused, true);
  storyNext(c);
  assert.strictEqual(greets.length, 1);       // nothing is pushed while it is held

  // story_more brings the next part, and the page goes on from there
  r = await liveToolCall(c, { functionCalls: [{ id: '2', name: 'story_more', args: {} }] });
  a = r.functionResponses[0].response;
  assert.ok(a.part.startsWith('Paragraph 3'), a.part);
  assert.strictEqual(a.more, true);
  assert.strictEqual(c.story.paused, false);
  c.story.sounded = true;
  storyNext(c);
  assert.ok(/Paragraph 4/.test(greets[1]) && /It is the end of the story/.test(greets[1]));
  assert.strictEqual(c.story, null);
  r = await liveToolCall(c, { functionCalls: [{ id: '3', name: 'story_more', args: {} }] });
  assert.strictEqual(r.functionResponses[0].response.done, true);

  // a call Live took back gets its story dropped, not told
  c = newTalk();
  c.toolGone = { 7: true };
  r = await liveToolCall(c, { functionCalls: [{ id: '7', name: 'tell_story', args: {} }] });
  assert.strictEqual(c.story, null);

  // other tools still reach the skills, next to the page's own
  c = newTalk();
  r = await liveToolCall(c, { functionCalls: [{ id: '4', name: 'story_more' }, { id: '5', name: 'remember_fact' }] });
  assert.deepStrictEqual(r.functionResponses.map(function (x) { return x.id; }), ['4', '5']);

  // end_talk: never answered, and it closes once her sound has drained
  c = newTalk();
  r = await liveToolCall(c, { functionCalls: [{ id: '6', name: 'end_talk' }] });
  assert.deepStrictEqual(r.functionResponses, []);
  assert.strictEqual(finished, 1);
  c = newTalk();
  c.story = { parts: ['a', 'b'], next: 1, paused: false, sounded: true, askedAt: clock };
  speaking = true;
  r = await liveToolCall(c, { functionCalls: [{ id: '6', name: 'end_talk' }] });
  assert.deepStrictEqual(r.functionResponses, []);
  assert.strictEqual(finished, 0);
  assert.strictEqual(c.ending, true);
  assert.strictEqual(c.story, null);
  speaking = false;
  liveSpeakingChanged(c, false);
  assert.strictEqual(finished, 1);
  assert.deepStrictEqual(greets, []);

  // end_talk while the page's own goodbye is still on its way: that goodbye is heard, then the talk closes
  c = newTalk();
  liveByeNow(c);
  await liveToolCall(c, { functionCalls: [{ id: '6', name: 'end_talk' }] });
  assert.strictEqual(finished, 0);
  speaking = true; liveSpeakingChanged(c, true);
  liveTurnDone(c);
  speaking = false; liveSpeakingChanged(c, false);
  assert.strictEqual(finished, 1);

  // both goodbyes at once only ever ask once
  c = newTalk();
  liveByeNow(c);
  liveByeNow(c);
  assert.strictEqual(greets.length, 1);

  // the emergency gate comes first, for the page's own tools too
  c = newTalk();
  S.screen = 'emergency';
  r = await liveToolCall(c, { functionCalls: [{ id: '6', name: 'end_talk' }, { id: '8', name: 'story_more' }] });
  assert.deepStrictEqual(r.functionResponses.map(function (x) { return x.response.error; }), ['emergency', 'emergency']);
  assert.strictEqual(c.ending, false);
  assert.strictEqual(finished, 0);
  c = newTalk();
  c.heardCheck = Promise.resolve({ emergency: true });
  r = await liveToolCall(c, { functionCalls: [{ id: '6', name: 'end_talk' }] });
  assert.strictEqual(r.functionResponses[0].response.error, 'emergency');
  assert.strictEqual(c.ending, false);

  // an emergency takes the talk back from a goodbye and ends a story
  c = newTalk();
  c.story = { parts: ['a', 'b'], next: 1, paused: false, sounded: true, askedAt: clock };
  liveHeardPiece(c, 'good night');
  liveEmergency(c, { say: 'CALL NOW' });
  assert.strictEqual(timers.size, 0);
  assert.strictEqual(c.story, null);
  assert.strictEqual(S.screen, 'emergency');
  assert.ok(/CALL NOW/.test(greets[0]));
  c = newTalk();
  liveByeNow(c);
  liveEmergency(c, { say: 'CALL NOW' });
  assert.strictEqual(c.ending, false);
  assert.strictEqual(timers.size, 0);
  liveTurnDone(c);
  assert.strictEqual(finished, 0);
  assert.strictEqual(S.convo, c);
  console.log('OK live block');
})().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
"""

VOICE_STUBS = r"""
const assert = require('assert');
var S = { convo: null, talkOrder: ['normal', 'offline'], talkMode: 'normal', voiceMode: 'normal', fallbackSaid: false,
  ttsSpent: false };
var Sp = { sess: null };
var MSG = { fallback: 'FALLBACK' };
var window = { MaryVoice: { more: function () {} } };
var said = [], closed = 0, pumps = 0, status = null;
function log() {}
function spPump() { pumps++; }
function spFinish() {}
function setPhase() {}
function goodbyeLine() { return 'GOODBYE'; }
function closeConvo(c) { closed++; c.ending = true; S.convo = null; }
function talkTo(t) { said.push(['talkTo', t]); return Promise.resolve(); }
function say(t, m, v) { said.push([t, v]); return Promise.resolve(); }
function api() { return status ? status() : Promise.resolve({ emergency: false }); }
function applyStatus(st) { if (st.tts_spent != null) { S.ttsSpent = !!st.tts_spent; } }
function session(voice) {
  var s = { voice: voice, queue: [], mvSent: ['a', 'b', 'c'], mvEnded: true, mvJob: {}, finished: false };
  Sp.sess = s;
  return s;
}
function fail(s, at) { var job = s.mvJob = {}; mvDone(s, job, { ok: false, kind: 'failed', at: at }); }
"""

VOICE_CHECKS = r"""
(async function () {
  // locked from a fresh status, and a slow or failed status uses what is known
  let c = { mode: 'normal', live: false, voice: null };
  S.convo = c;
  status = function () { return Promise.resolve({ tts_spent: true }); };
  await lockTalkVoice(c);
  assert.strictEqual(c.voice, 'offline');
  assert.strictEqual(S.voiceMode, 'offline');
  assert.strictEqual(speechVoice(), 'offline');
  c = { mode: 'normal', live: false, voice: null };
  S.convo = c;
  status = function () { return Promise.resolve({ tts_spent: false }); };
  await lockTalkVoice(c);
  assert.strictEqual(c.voice, 'normal');
  status = function () { return Promise.reject(new Error('slow')); };
  c = { mode: 'normal', live: false, voice: null };
  S.convo = c;
  await lockTalkVoice(c);
  assert.strictEqual(c.voice, 'normal');
  status = null;

  // a real failure part way: the talk moves once, the next reply stays there, and the fallback line comes once
  S.fallbackSaid = false;
  let s = session('normal');
  fail(s, 1);
  assert.strictEqual(c.voice, 'offline');
  assert.strictEqual(s.voice, 'offline');
  assert.deepStrictEqual(s.queue, ['FALLBACK', 'b', 'c']);
  assert.strictEqual(pumps, 1);                // she goes on with what wasn't said, so the reply ends and she listens
  assert.strictEqual(speechVoice(), 'offline');
  s = session(speechVoice());
  fail(s, 0);
  assert.strictEqual(c.voice, '');             // only now the computer's own voice
  assert.deepStrictEqual(s.queue, ['a', 'b', 'c']);
  assert.strictEqual(speechVoice(), '');
  S.voiceMode = 'normal';                      // never back
  assert.strictEqual(speechVoice(), '');

  // the server's own swap: no failure, no line, and the talk stays on Kokoro
  c = { mode: 'normal', live: false, voice: 'normal' };
  S.convo = c;
  S.voiceMode = 'normal';
  S.ttsSpent = false;
  S.fallbackSaid = false;
  s = session('normal');
  voiceSwapped(s, 'offline');
  assert.strictEqual(c.voice, 'offline');
  assert.strictEqual(s.voice, 'offline');
  assert.strictEqual(S.ttsSpent, true);
  assert.strictEqual(S.fallbackSaid, false);
  assert.strictEqual(speechVoice(), 'offline');

  // a voice failure never touches a Live talk
  c = { mode: 'live', live: true, voice: null };
  S.convo = c;
  S.talkMode = 'live';
  S.talkOrder = ['live', 'normal', 'offline'];
  S.voiceMode = 'normal';
  s = session('offline');
  fail(s, 0);
  assert.strictEqual(c.voice, null);
  assert.strictEqual(c.live, true);

  // with Live chosen, lines outside a talk are Kokoro or the computer's own voice, never Gemini TTS
  S.convo = null;
  assert.strictEqual(speechVoice(), 'offline');
  S.talkOrder = ['live', 'normal'];
  assert.strictEqual(speechVoice(), '');
  // ... but a talk that really fell back from Live to Normal uses Normal
  S.talkOrder = ['live', 'normal', 'offline'];
  S.convo = { mode: 'normal', live: false, voice: 'normal' };
  assert.strictEqual(speechVoice(), 'normal');

  // a spoken goodbye ends a Normal talk in that talk's voice, after the emergency check
  c = { mode: 'normal', live: false, voice: 'offline' };
  S.convo = c;
  S.voiceMode = 'normal';
  said = [];
  await convoBye(c, 'go to sleep');
  assert.strictEqual(closed > 0 && S.convo === null, true);
  assert.deepStrictEqual(said, [['GOODBYE', 'offline']]);
  c = { mode: 'normal', live: false, voice: 'normal' };
  S.convo = c;
  said = [];
  status = function () { return Promise.resolve({ emergency: true }); };
  await convoBye(c, 'go to sleep');
  assert.deepStrictEqual(said, [['talkTo', 'go to sleep']]);
  console.log('OK one voice');
})().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
"""

SWAP_CHECKS = r"""
const assert = require('assert');
global.window = global;
window.addEventListener = function () {};
class FakeCtx {
  constructor() { this.state = 'running'; this.currentTime = 0; this.destination = {}; }
  createGain() { return { gain: { value: 1 }, connect() {} }; }
  createBuffer(c, n, r) { return { duration: n / r, getChannelData() { return new Float32Array(n); } }; }
  createBufferSource() { return { playbackRate: { value: 1 }, connect() {}, disconnect() {}, start() {}, stop() {} }; }
}
window.AudioContext = FakeCtx;
let asked = [], voice = 'offline';
global.fetch = function (url, init) {
  asked.push(JSON.parse(init.body).mode);
  const h = { 'X-Rate': '24000', 'X-Channels': '1', 'X-Mary-Voice': voice };
  return Promise.resolve({ ok: true, status: 200, headers: { get: function (k) { return h[k] || null; } }, body: null,
    arrayBuffer: function () { return Promise.resolve(new ArrayBuffer(4800)); } });
};
//VOICEOUT
function wait() { return new Promise(function (ok) { setTimeout(ok, 60); }); }
(async function () {
  const told = [];
  window.MaryVoice.queue(['One.', 'Two.', 'Three.'], { mode: 'normal', onVoice: function (v) { told.push(v); } });
  await wait();
  assert.deepStrictEqual(told, ['offline']);       // told once
  assert.strictEqual(asked[0], 'normal');
  assert.ok(asked.length >= 2);
  asked.slice(1).forEach(function (m) { assert.strictEqual(m, 'offline'); });
  window.MaryVoice.cancel();
  asked = []; voice = 'normal'; told.length = 0;
  window.MaryVoice.queue(['One.', 'Two.'], { mode: 'normal', onVoice: function (v) { told.push(v); } });
  await wait();
  assert.deepStrictEqual(told, []);
  asked.forEach(function (m) { assert.strictEqual(m, 'normal'); });
  window.MaryVoice.cancel();
  asked = []; voice = 'offline';
  window.MaryVoice.queue(['One.'], { mode: 'offline', onVoice: function (v) { told.push(v); } });
  await wait();
  assert.deepStrictEqual(told, []);                // she asked for Kokoro: nothing was swapped
  window.MaryVoice.cancel();
  console.log('OK swap');
  process.exit(0);
})().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
"""


def find_node():
    node = shutil.which("node")
    if node:
        return node
    for base in (os.environ.get("ProgramFiles"), r"C:\Program Files"):
        if base:
            p = os.path.join(base, "nodejs", "node.exe")
            if os.path.isfile(p):
                return p
    return None


def between(src, start, end):
    a = src.index(start)
    return src[a:src.index(end, a)]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


NODE = find_node()


@unittest.skipUnless(NODE, "Node not found: the story checks were skipped")
class StoryJsTests(unittest.TestCase):
    def run_node(self, code):
        # stdin, not -e: the whole script can be longer than a Windows command line
        run = subprocess.run([NODE, "-"], input=code, capture_output=True, text=True, encoding="utf-8",
                             timeout=30, cwd=ROOT)
        out = (run.stdout + run.stderr).strip()
        self.assertEqual(run.returncode, 0, out[-1500:])
        self.assertTrue(run.stdout.strip().startswith("OK "), out[-500:])

    def speech_parts(self, src):
        return [between(src, "function cleanSpeech(", "function estimateMs("),
                between(src, "var ABBR = {", "function addTimer(")]

    def test_story_helpers(self):
        src = read(APP)
        cases = [[t, mary.not_english(t)] for t in SCRIPTS]
        self.assertTrue(any(c[1] for c in cases) and not all(c[1] for c in cases))
        code = "\n".join(self.speech_parts(src) + [
            between(src, "function nextMode(", "// What to do with Live's skill call"),
            between(src, "// --- M4a story helpers", "// --- end M4a story helpers"),
            "const CASES = " + json.dumps(cases) + ";",
            CHECKS,
        ])
        self.run_node(code)

    def test_goodbye_phrases(self):
        src = read(APP)
        code = "\n".join([
            between(src, "var BYE_MAX_WORDS", "var LIVE_BYE_MAX_MS"),
            between(src, "function isGoodbye(", "function liveSupported("),
            BYE_CHECKS,
        ])
        self.run_node(code)

    def test_live_goodbyes_and_stories(self):
        """The real goodbye, story and tool code of the Live block, with the page around it stubbed."""
        src = read(APP)
        code = "\n".join(self.speech_parts(src) + [
            LIVE_STUBS,
            between(src, "var SILENCE_NOISE", "// --- M4a: hands-free conversations"),
            between(src, "var BYE_MAX_WORDS", "// M4a: {when} is the local time of day"),
            between(src, "function nextMode(", "// What to do with Live's skill call"),
            between(src, "function liveToolGate(", "// A short goodbye turn"),
            between(src, "function isGoodbye(", "function liveSupported("),
            between(src, "function liveSpeakingChanged(", "// M4a: her finished Live turn is remembered"),
            between(src, "function liveEmergency(", "function liveToolCall("),
            between(src, "function liveToolCall(", "// Typed words while Live is open"),
            LIVE_CHECKS,
        ])
        self.run_node(code)

    def test_one_voice_for_a_talk(self):
        src = read(APP)
        code = "\n".join(self.speech_parts(src) + [
            VOICE_STUBS,
            between(src, "function nextMode(", "// What to do with Live's skill call"),
            between(src, "var TOOL_REFUSED", "function storyTake("),
            between(src, "function voiceFor(", "// One open MaryVoice job"),
            between(src, "// M4a: the server made this line in Kokoro", "function spPump("),
            between(src, "// M4a: decides c.voice", "function closeConvo("),
            between(src, "function convoBye(", "function convoAfterEmergency("),
            VOICE_CHECKS,
        ])
        self.run_node(code)

    def test_voiceout_tells_the_page_about_a_swap(self):
        self.run_node(SWAP_CHECKS.replace("//VOICEOUT", read(VOICEOUT)))

    def test_one_voice_in_live(self):
        src, talklive = read(APP), read(TALKLIVE)
        for gone in ("storyStop", "storyPlay", "storyWait", "storyDone", "storyIgnore", "storyEcho", "storyAnswer",
                     "storyPlaying", "storyChunks", "STORY_TOLD", "liveByeRelease", "byeHold", "heldTool"):
            self.assertNotIn(gone, src)
        self.assertNotIn("hush(", talklive)
        self.assertNotIn("s.hushed", talklive)
        live = between(src, "// --- M4a: in Live, Live speaks everything", "function liveToolCall(")
        self.assertNotIn("MaryVoice", live)
        self.assertNotIn("goodbyeLine", live)
        self.assertNotIn(" say(", live)
        # the two Normal and Offline ways out both keep the talk's voice
        self.assertEqual(src.count("say(goodbyeLine(), 'happy', voice)"), 2)
        self.assertEqual(src.count("say(goodbyeLine()"), 2)


if __name__ == "__main__":
    unittest.main()
