// Coin flip's page half: shows the coin and plays its effects. All its state lives on the server.
MarySkills.register('coin_flip', {
  enter(el) {
    el.innerHTML = '<div class="coin-flip" aria-live="polite">Tap the coin to flip it</div>';
  },
  leave(el) {
    el.innerHTML = '';
  },
  effect(kind, data) {
    if (kind !== 'coin') return;
    const box = document.querySelector('.coin-flip');
    if (box && data.side) box.textContent = 'It\'s ' + data.side + '!';
  }
});
