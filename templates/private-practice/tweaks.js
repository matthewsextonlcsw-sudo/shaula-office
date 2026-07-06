/* ═══════════════════════════════════════════════════════════════════
   Tweaks panel — vanilla-JS, host-protocol-compliant.
   Lets you adjust the hawks band live (height, focus, treatments).
   ═══════════════════════════════════════════════════════════════════ */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "bandHeightVh": 56,
  "bandObjectPosY": 30,
  "bandFadeStrength": 0.65,
  "bandFadeHeight": 32,
  "bandGradeWarmth": 0.45,
  "bandKenBurns": true,
  "bandRoundedBottom": 0,
  "showSunriseRule": true
}/*EDITMODE-END*/;

let TWEAKS = { ...TWEAK_DEFAULTS };

/* ───── apply tweaks to the DOM ───── */
function applyTweaks(){
  const root = document.documentElement;
  root.style.setProperty('--band-h', `${TWEAKS.bandHeightVh}vh`);
  root.style.setProperty('--band-pos-y', `${TWEAKS.bandObjectPosY}%`);
  root.style.setProperty('--band-fade-strength', String(TWEAKS.bandFadeStrength));
  root.style.setProperty('--band-fade-h', `${TWEAKS.bandFadeHeight}%`);
  root.style.setProperty('--band-grade-warmth', String(TWEAKS.bandGradeWarmth));
  root.style.setProperty('--band-radius', `${TWEAKS.bandRoundedBottom}px`);

  const v = document.querySelector('.hawks-video');
  if(v){
    v.style.animationPlayState = TWEAKS.bandKenBurns ? 'running' : 'paused';
    if(!TWEAKS.bandKenBurns){
      v.style.transform = 'scale(1.02)';
    } else {
      v.style.transform = '';
    }
  }
  const sr = document.querySelector('.sunrise-rule.wide');
  if(sr){ sr.style.display = TWEAKS.showSunriseRule ? '' : 'none'; }
}

/* ───── persist a key change to disk via host postMessage ───── */
function setTweak(key, val){
  TWEAKS[key] = val;
  applyTweaks();
  try {
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits: { [key]: val } }, '*');
  } catch(e) {}
}

/* ───── build the panel ───── */
function buildPanel(){
  const panel = document.createElement('div');
  panel.className = 'tw-panel';
  panel.innerHTML = `
    <div class="tw-head">
      <span class="tw-title">Tweaks</span>
      <button class="tw-close" aria-label="Close tweaks">×</button>
    </div>
    <div class="tw-body">
      <div class="tw-section">
        <h4>Hawks band</h4>
        <label class="tw-row">
          <span>Height</span>
          <input type="range" data-key="bandHeightVh" min="24" max="100" step="1" value="${TWEAKS.bandHeightVh}"/>
          <span class="tw-val" data-bind="bandHeightVh">${TWEAKS.bandHeightVh}vh</span>
        </label>
        <label class="tw-row">
          <span>Vertical focus</span>
          <input type="range" data-key="bandObjectPosY" min="0" max="100" step="1" value="${TWEAKS.bandObjectPosY}"/>
          <span class="tw-val" data-bind="bandObjectPosY">${TWEAKS.bandObjectPosY}%</span>
        </label>
        <label class="tw-row">
          <span>Bottom fade</span>
          <input type="range" data-key="bandFadeStrength" min="0" max="1" step="0.05" value="${TWEAKS.bandFadeStrength}"/>
          <span class="tw-val" data-bind="bandFadeStrength">${TWEAKS.bandFadeStrength}</span>
        </label>
        <label class="tw-row">
          <span>Fade height</span>
          <input type="range" data-key="bandFadeHeight" min="10" max="60" step="1" value="${TWEAKS.bandFadeHeight}"/>
          <span class="tw-val" data-bind="bandFadeHeight">${TWEAKS.bandFadeHeight}%</span>
        </label>
        <label class="tw-row">
          <span>Warm grade</span>
          <input type="range" data-key="bandGradeWarmth" min="0" max="1" step="0.05" value="${TWEAKS.bandGradeWarmth}"/>
          <span class="tw-val" data-bind="bandGradeWarmth">${TWEAKS.bandGradeWarmth}</span>
        </label>
        <label class="tw-row">
          <span>Rounded bottom</span>
          <input type="range" data-key="bandRoundedBottom" min="0" max="48" step="1" value="${TWEAKS.bandRoundedBottom}"/>
          <span class="tw-val" data-bind="bandRoundedBottom">${TWEAKS.bandRoundedBottom}px</span>
        </label>
        <label class="tw-toggle">
          <input type="checkbox" data-key="bandKenBurns" ${TWEAKS.bandKenBurns ? 'checked' : ''}/>
          <span>Slow zoom (Ken Burns)</span>
        </label>
      </div>
      <div class="tw-section">
        <h4>Hero accents</h4>
        <label class="tw-toggle">
          <input type="checkbox" data-key="showSunriseRule" ${TWEAKS.showSunriseRule ? 'checked' : ''}/>
          <span>Sunrise rule above H1</span>
        </label>
      </div>
    </div>
  `;
  document.body.appendChild(panel);

  // wire ranges
  panel.querySelectorAll('input[type="range"]').forEach(inp => {
    inp.addEventListener('input', () => {
      const key = inp.dataset.key;
      const val = parseFloat(inp.value);
      const bind = panel.querySelector(`[data-bind="${key}"]`);
      if(bind){
        const suffix = key === 'bandHeightVh' ? 'vh'
                     : key === 'bandObjectPosY' ? '%'
                     : key === 'bandFadeHeight' ? '%'
                     : key === 'bandRoundedBottom' ? 'px'
                     : '';
        bind.textContent = val + suffix;
      }
      setTweak(key, val);
    });
  });
  // wire checkboxes
  panel.querySelectorAll('input[type="checkbox"]').forEach(inp => {
    inp.addEventListener('change', () => {
      setTweak(inp.dataset.key, inp.checked);
    });
  });
  // close
  panel.querySelector('.tw-close').addEventListener('click', () => {
    panel.classList.remove('open');
    try { window.parent.postMessage({ type: '__edit_mode_dismissed' }, '*'); } catch(e) {}
  });

  return panel;
}

/* ───── host protocol: register listener BEFORE announcing ───── */
let _panel = null;
window.addEventListener('message', (e) => {
  const msg = e.data || {};
  if(msg.type === '__activate_edit_mode'){
    if(!_panel) _panel = buildPanel();
    _panel.classList.add('open');
  } else if(msg.type === '__deactivate_edit_mode'){
    if(_panel) _panel.classList.remove('open');
  }
});

/* ───── apply defaults immediately so the page reflects them ───── */
applyTweaks();

/* ───── announce availability ───── */
try {
  window.parent.postMessage({ type: '__edit_mode_available' }, '*');
} catch(e) {}
