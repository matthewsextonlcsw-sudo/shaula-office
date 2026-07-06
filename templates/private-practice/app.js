/* ─────────────────────────────────────────────────────────────
   Solo Private-Practice Template — single-page interactive prototype
   Client-side routing, content templates, motion, form.
   Owner-specific text lives as double-curly tokens and AI-GENERATE comment blocks.
   ───────────────────────────────────────────────────────────── */

// ============ ROUTE TEMPLATES ============
const routes = {};

routes.home = () => `
  <!-- HERO -->
  <section class="hero" aria-labelledby="h1" data-kh data-kh-tagline="{{tagline}}" data-kh-specialties="{{specialties}}" data-kh-populations="{{populations}}">
    <!-- Hero band — full-width ambient banner from below nav down to where the H1 begins.
         Default asset is the bundled nature clip (assets/hawks-hero.mp4) — part of the template's
         visual style. {{upload}} OPTIONAL: to use a custom hero video, replace assets/hawks-hero.mp4
         (keep the filename) and update the aria-label below. Static fallback: assets/hawks-sky.png (CSS). -->
    <div class="hawks-band">
      <video class="hawks-video" autoplay muted loop playsinline preload="auto" data-src="assets/hawks-hero.mp4" aria-label="{{hero_video_alt}}"></video>
      <div class="hawks-fallback" aria-hidden="true"></div>
      <div class="hawks-grade" aria-hidden="true"></div>
      <div class="hawks-fade" aria-hidden="true"></div>
    </div>
    <div class="hero-inner">
      <div class="hero-content">
        <span class="hero-eyebrow"><span class="dot"></span> {{availability_status}} · {{service_areas}} telehealth</span>
        <span class="sunrise-rule wide"></span>
        <!-- AI-GENERATE:hero_headline | Write a short, evocative hero headline (5-9 words) for the private psychotherapy practice of {{owner_name}}, {{credential}}, specializing in {{specialties}}. Optionally split with an emphasis phrase. Voice: calm, literary, peer-to-peer clinician — not marketing fluff. Wrap the emphasis half in <span class="accent">…</span>. Return only the inner HTML for the <h1>. -->
        <h1 id="h1">A different kind of <span class="accent">therapeutic work.</span></h1>
        <!-- AI-GENERATE:hero_sub | Write a 1-2 sentence hero subhead for {{owner_name}}, {{credential}}, a {{practice_model}} psychotherapist. Name who they serve ({{populations}}) and the core stance (evidence-based, structured). Voice: plain, direct, warm. End-state should read like a clinician talking to a prospective client, not an ad. -->
        <p class="hero-sub">{{practice_model}} private psychotherapy with {{owner_name}}, {{credential}}. Evidence-based work for adults at a turning point.</p>
        <div class="hero-actions">
          <a class="btn btn-primary" data-route="contact" href="#contact">Request a consult <span class="arrow">→</span></a>
          <a class="btn btn-ghost" data-route="method" href="#method">See the method</a>
        </div>
      </div>
      <div class="hero-meta" aria-hidden="true">
        {{location}} · Telehealth {{service_areas}}<br/>
        {{session_fee}} / {{session_length}} session · {{practice_model}}<br/>
        {{response_time}}
      </div>
    </div>
  </section>

  <!-- QUICK FACTS -->
  <div class="qf-wrap">
    <div class="qf glass" role="region" aria-label="Quick facts">
      <div class="item">
        <span class="label">Office</span>
        <span class="value">{{location}} <small>{{office_detail}}</small></span>
      </div>
      <div class="item">
        <span class="label">Telehealth</span>
        <span class="value">{{service_areas}}</span>
      </div>
      <div class="item">
        <span class="label">Fee</span>
        <span class="value">{{session_fee}} <small>{{session_length}} · {{payment_model_short}}</small></span>
      </div>
      <div class="item">
        <span class="label">Cadence</span>
        <span class="value">{{cadence}} <small>or as clinically indicated</small></span>
      </div>
    </div>
  </div>

  <!-- METHOD INTRO -->
  <!-- AI-GENERATE:method_intro_cards | The practice has a named signature framework: {{method_name}} ({{method_acronym}}). Produce a JS array literal of [letter, short-name, one-sentence-description] tuples — one per letter of {{method_acronym}} (so the acronym spells out down the cards). Each description: one plain, clinically-grounded sentence (<=14 words). If the practice has NO signature method, instead output 4-6 tuples describing the core stages of their therapeutic approach for {{specialties}}, and the parent FILL_MANIFEST should swap the eyebrow/heading copy accordingly. Replace the placeholder array below. -->
  <section class="reveal">
    <div class="wrap">
      <div class="sweep-rule"></div>
      <div class="section-head">
        <span class="eyebrow">{{method_name}}</span>
        <!-- AI-GENERATE:method_intro_heading | One short declarative heading (<=8 words) capturing what {{method_name}} does for the client. -->
        <h2 class="display">A simple framework for the hard moments.</h2>
        <!-- AI-GENERATE:method_intro_lede | One sentence: who built {{method_name}} ({{owner_name}}) and the clinical moment it targets. Plain, no jargon. -->
        <p class="lede">An evidence-informed framework {{owner_name}} uses with clients for the moment most therapy doesn't reach.</p>
      </div>

      <div class="stoick-grid">
        ${[
          ['1','Step one','Replace with the first move of {{method_name}}.'],
          ['2','Step two','Replace with the second move of {{method_name}}.'],
          ['3','Step three','Replace with the third move of {{method_name}}.'],
          ['4','Step four','Replace with the fourth move of {{method_name}}.'],
          ['5','Step five','Replace with the fifth move of {{method_name}}.'],
          ['6','Step six','Replace with the sixth move of {{method_name}}.']
        ].map((c,i)=>`
          <div class="stoick-card">
            <span class="num">${String(i+1).padStart(2,'0')}</span>
            <div class="letter">${c[0]}</div>
            <div class="name">${c[1]}</div>
            <div class="desc">${c[2]}</div>
          </div>`).join('')}
      </div>

      <div style="margin-top:36px;">
        <a class="text-link" data-route="method" href="#method">Read the full method, with the science behind each move →</a>
      </div>
    </div>
  </section>

  <!-- WHO -->
  <section class="reveal">
    <div class="wrap">
      <div class="sweep-rule"></div>
      <div class="two-col">
        <div>
          <span class="eyebrow">Who I work with</span>
          <!-- AI-GENERATE:who_heading | One warm declarative heading (<=10 words) describing the kind of client {{owner_name}} works with. May use <em>…</em> for emphasis. -->
          <h2 class="display" style="margin-top:14px;">People at a turning point who are ready to <em>move</em>.</h2>
        </div>
        <div>
          <!-- AI-GENERATE:who_body | Write a 2-3 sentence paragraph describing who comes to {{business_name}} and what they're looking for in a clinician. Specialties: {{specialties}}. Voice: plain, perceptive, peer-to-peer; never salesy. -->
          <p class="lead muted">Most clients arrive having already tried hard. They want a clinician who meets that with structure, evidence, and a steady hand.</p>
          <div class="populations" style="margin-top:28px;">
            <!-- AI-GENERATE:populations_chips | Output a JS array of 6-8 short population/specialty labels (1-3 words each, HTML-escaped) that {{business_name}} serves, derived from {{specialties}} and {{populations}}. Replace the array below. -->
            ${['Specialty one','Specialty two','Specialty three','Specialty four','Specialty five','Specialty six'].map(p=>`<span class="chip"><span class="dot"></span>${p}</span>`).join('')}
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- PULL QUOTE -->
  <!-- AI-GENERATE:pull_quote | Write a single resonant 1-2 sentence pull-quote in the clinical voice of {{owner_name}}, {{credential}}, that captures their philosophy toward {{specialties}}. Literary, warm, true — the kind of line a client remembers. Keep it inside the <blockquote> below. -->
  <section class="tight">
    <div class="pullquote reveal">
      <span class="sunrise-rule wide center"></span>
      <blockquote>"The work isn't about becoming someone new. It's about getting the obstacles out of the way of who you already are."</blockquote>
      <cite>— {{owner_name}}, {{credential}}</cite>
    </div>
  </section>

  <!-- WRITING -->
  <section class="reveal">
    <div class="wrap">
      <div class="sweep-rule"></div>
      <div class="section-head" style="display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:24px;max-width:none;">
        <div>
          <span class="eyebrow">Writing</span>
          <h2 class="display" style="margin-top:14px;">Field notes from the practice.</h2>
        </div>
        <a class="text-link" data-route="writing" href="#writing">All posts →</a>
      </div>
      ${postCards(posts.slice(0,3))}
    </div>
  </section>

  <!-- CONTACT STRIP -->
  ${contactStrip()}
`;

// ============ ABOUT ============
routes.about = () => `
  <section class="tall">
    <div class="wrap">
      <span class="sunrise-rule wide"></span>
      <div class="bio-grid">
        <div>
          <!-- {{upload}} HEADSHOT: replace assets/placeholder-headshot.svg with a real portrait (JPG/PNG, portrait orientation ~800x1000) and update the filename in the url() below. The styled frame + caption stay. -->
          <div class="portrait" aria-label="Portrait of {{owner_name}}" style="background-image:url('assets/placeholder-headshot.svg');background-size:cover;background-position:center;">
            <span class="placeholder">Portrait — {{owner_name}}, {{credential}} · {{upload}}</span>
          </div>
          <div class="facts-list" style="margin-top:24px;">
            <div class="fact-row"><span class="k">Credential</span><span class="v">{{credential}}</span></div>
            <div class="fact-row"><span class="k">{{license_1_label}}</span><span class="v mono">{{license_1_value}}</span></div>
            <div class="fact-row"><span class="k">{{license_2_label}}</span><span class="v mono">{{license_2_value}}</span></div>
            <div class="fact-row"><span class="k">Education</span><span class="v">{{education}}</span></div>
            <div class="fact-row"><span class="k">Founded</span><span class="v">{{business_name}} · {{founded_date}}</span></div>
            <div class="fact-row"><span class="k">Office</span><span class="v">{{address_full}}</span></div>
            <div class="fact-row"><span class="k">Phone</span><span class="v mono">{{phone}}</span></div>
          </div>
        </div>
        <div>
          <span class="eyebrow">About</span>
          <!-- AI-GENERATE:about_headline | Write a single sentence (15-25 words) framing who {{owner_name}}, {{credential}}, is and the throughline of their clinical work in {{specialties}}. Reads as a display headline. Plain, specific, no cliché. -->
          <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,68px);">{{owner_name}} is a {{credential_full}} who does structured, evidence-based work with people at a turning point.</h1>
          <div class="spacer-md"></div>
          <!-- AI-GENERATE:about_body | Write a 3-paragraph "about" for {{owner_name}}, {{credential}}, of {{business_name}}. P1: their professional background / the rooms they've worked in ({{background_summary}}). P2: founding {{business_name}} ({{founded_date}}), who they see now ({{specialties}}), and where ({{location}} + telehealth across {{service_areas}}). P3: their approach ({{modalities}}) and the human philosophy under it; reference {{method_name}} and {{program_name}} as their own frameworks. Voice: peer-to-peer clinician, plain, grounded, no marketing fluff. Each paragraph in its own <p>; first <p class="lead">. -->
          <p class="lead">{{owner_name}}, {{credential}}, has spent years in clinical settings where the work mattered too much to be vague.</p>
          <p style="margin-top:20px;">{{owner_name}} founded {{business_name}} and now sees adults privately for {{specialties}}. Licensed to serve {{service_areas}}, with telehealth and an in-person office in {{location}}.</p>
          <p style="margin-top:20px;">The approach is evidence-based and outcomes-tracked — {{modalities}} — but the soul of it is simpler: people who do the work deserve a clinician who will too.</p>

          <div class="callout" style="margin-top:40px;">
            <span class="eyebrow">A note from {{owner_first_name}}</span>
            <!-- AI-GENERATE:about_note | Write a short first-person note (2-3 sentences) from {{owner_name}} on how they hold the work and who it's for. Warm, direct, a little personal. Inside the <p> below, in quotes. -->
            <p>"I take this work seriously, and I expect the people I work with to do the same. If you're ready for that, I'm a good clinician to do it with."</p>
          </div>
        </div>
      </div>

      <div class="spacer-lg"></div>
      <span class="sunrise-rule wide"></span>
      <!-- AI-GENERATE:career_heading | One short heading (<=8 words) introducing {{owner_name}}'s career arc. -->
      <h2 class="display">A career arc that built this practice.</h2>
      <!-- AI-GENERATE:career_lede | One sentence summarizing the throughline of {{owner_name}}'s career and how it informs private practice today. -->
      <p class="lede" style="margin-top:14px;color:var(--ink-2);max-width:62ch;">Each chapter taught a different piece of what this practice now is.</p>
      <div class="spacer-md"></div>

      <div class="timeline">
        <!-- AI-GENERATE:career_timeline | Output a JS array of 4-6 tuples [years, organization, role, one-sentence accomplishment] representing {{owner_name}}'s career history, most recent last (ending with founding {{business_name}}). Pull from {{career_history}} in practice.md. Each accomplishment: one factual sentence. Replace the placeholder array below. -->
        ${[
          ['Year – Year','Organization','Role','One-sentence description of the work and a concrete accomplishment.'],
          ['Year – Year','Organization','Role','One-sentence description of the work and a concrete accomplishment.'],
          ['Year – Year','Organization','Role','One-sentence description of the work and a concrete accomplishment.'],
          ['Founded – present','{{business_name}}','Founder · Private Practice','Private practice serving {{specialties}}. Licensed for {{service_areas}}.']
        ].map(t=>`
          <div class="t-item">
            <div class="yr">${t[0]}</div>
            <h4>${t[1]}</h4>
            <div class="org">${t[2]}</div>
            <p>${t[3]}</p>
          </div>`).join('')}
      </div>
    </div>
  </section>

  ${contactStrip()}
`;

// ============ APPROACH ============
routes.approach = () => `
  <section class="tall">
    <div class="wrap">
      <span class="sunrise-rule wide"></span>
      <span class="eyebrow">Approach</span>
      <!-- AI-GENERATE:approach_headline | One short display headline (3-6 words) describing {{owner_name}}'s therapeutic approach. -->
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:18ch;">Evidence-based, outcomes-tracked, and quietly demanding.</h1>
      <!-- AI-GENERATE:approach_intro | Write 1-2 sentences on how {{owner_name}} uses the modalities below in combination, and (if applicable) how outcomes are tracked ({{outcome_measures}}). Plain and confident. -->
      <p class="lead muted" style="margin-top:24px;">Every modality below is supported by peer-reviewed research and used in combination — not as a brand.</p>

      <div class="spacer-lg"></div>

      <div class="modality-grid">
        <!-- AI-GENERATE:modalities | Output a JS array of 4-6 tuples [short-tag, full-name, what-it-does-sentence, "Author — Source"] for the therapeutic modalities {{owner_name}} actually practices (from {{modalities}}). Each "what" sentence: plain-language, 1-2 sentences, clinically accurate. Citation = a real foundational reference for that modality. Replace the placeholder array below. Only include modalities the clinician is genuinely trained in. -->
        ${[
          ['M1','Modality One','One to two plain-language sentences on what this modality does and when it helps.','Author — Source'],
          ['M2','Modality Two','One to two plain-language sentences on what this modality does and when it helps.','Author — Source'],
          ['M3','Modality Three','One to two plain-language sentences on what this modality does and when it helps.','Author — Source'],
          ['M4','Modality Four','One to two plain-language sentences on what this modality does and when it helps.','Author — Source']
        ].map(m=>`
          <div class="modality">
            <span class="tag">${m[0]}</span>
            <h3>${m[1]}</h3>
            <p class="what">${m[2]}</p>
            <div class="cite">Evidence base · ${m[3]}</div>
          </div>`).join('')}
      </div>

      <div class="spacer-lg"></div>
      <div class="two-col">
        <div>
          <span class="sunrise-rule"></span>
          <h2 class="display">What this looks like in a session.</h2>
        </div>
        <div>
          <!-- AI-GENERATE:session_shape | Write 2 short paragraphs describing the shape of a session at {{business_name}}: length ({{session_length}}), what the first sessions cover, and the typical session structure. Reference {{outcome_measures}} if the practice tracks them. End on the practice's stance (e.g., trauma-informed, client-paced). Each paragraph its own <p>; first <p class="lead muted">. -->
          <p class="lead muted">Sessions are {{session_length}}. The first few are assessment-heavy — history, goals, and a baseline. From there, sessions are structured but not rigid: a check-in, the agreed clinical work, a between-session practice, and a brief close.</p>
          <p style="margin-top:18px;">Trauma-informed throughout. Pace is set by the client's nervous system, not the calendar.</p>
        </div>
      </div>
    </div>
  </section>

  ${contactStrip()}
`;

// ============ METHOD ============
routes.method = () => `
  <section class="tall">
    <div class="wrap">
      <span class="sunrise-rule wide"></span>
      <span class="eyebrow">{{method_name}}</span>
      <!-- AI-GENERATE:method_headline | One short display headline (4-8 words) capturing the core promise of {{method_name}}. -->
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:16ch;">A framework for the hard moments.</h1>
      <!-- AI-GENERATE:method_intro | Write 1-2 sentences introducing {{method_name}} as {{owner_name}}'s own framework: what it helps clients do, and that each step pairs the underlying science with a practice they can try this week. -->
      <p class="lead muted" style="margin-top:24px;max-width:62ch;">The framework {{owner_name}} uses with clients to interrupt automatic patterns and choose a response that fits who they actually are. Each step pairs the science with one practice you can run this week.</p>

      <div class="spacer-lg"></div>

      <!-- AI-GENERATE:method_steps | Output a JS array of tuples [letter-or-number, step-name, step-number-string, one-line-subtitle, science-paragraph, try-this-week-practice] — one per step of {{method_name}} (use {{method_acronym}} if it's an acronym, so the letters spell it out). science-paragraph: 2-4 sentences, clinically/neuroscience grounded, plain. practice: one concrete action. If the practice has NO named method, build 4-6 steps describing their core therapeutic process for {{specialties}}. Replace the placeholder array below. -->
      ${[
        ['1','Step one','01','One-line subtitle for this step',
          'Replace with a 2-4 sentence, plain-language explanation of what happens in this step and the science behind it.',
          'Replace with one concrete practice the reader can try this week.'],
        ['2','Step two','02','One-line subtitle for this step',
          'Replace with a 2-4 sentence, plain-language explanation of what happens in this step and the science behind it.',
          'Replace with one concrete practice the reader can try this week.'],
        ['3','Step three','03','One-line subtitle for this step',
          'Replace with a 2-4 sentence, plain-language explanation of what happens in this step and the science behind it.',
          'Replace with one concrete practice the reader can try this week.'],
        ['4','Step four','04','One-line subtitle for this step',
          'Replace with a 2-4 sentence, plain-language explanation of what happens in this step and the science behind it.',
          'Replace with one concrete practice the reader can try this week.']
      ].map(m=>`
        <div class="method-row">
          <div class="method-letter">${m[0]}</div>
          <div>
            <div class="method-name"><small>Step ${m[2]}</small>${m[1]}<br/><span style="font-size:18px;font-style:italic;color:var(--ink-2);font-weight:400;">${m[3]}</span></div>
          </div>
          <div>
            <p>${m[4]}</p>
            <div class="practice">
              <span class="lbl">Try this week</span>
              ${m[5]}
            </div>
          </div>
        </div>`).join('')}

      <div class="spacer-lg"></div>
      <div class="callout">
        <span class="eyebrow">Why this name</span>
        <!-- AI-GENERATE:method_why | Write a short first-person note (2-3 sentences) from {{owner_name}} explaining why {{method_name}} is named what it is and the one principle that makes it stick. If there's no named method, summarize the through-principle of the approach instead. Inside the <p> below, in quotes. -->
        <p>"The name is a reminder of the one principle that holds the whole thing together — and the part most people skip."</p>
      </div>
    </div>
  </section>

  ${contactStrip()}
`;

// ============ JOURNEY ============
routes.journey = () => `
  <section class="tall">
    <div class="wrap">
      <span class="sunrise-rule wide"></span>
      <span class="eyebrow">{{program_name}}</span>
      <!-- AI-GENERATE:journey_headline | One display headline (8-14 words) describing {{program_name}} — {{owner_name}}'s structured multi-phase therapy program. Mention the duration ({{program_duration}}) if it reads naturally. -->
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:18ch;">A structured journey for people ready to do real work.</h1>
      <!-- AI-GENERATE:journey_intro | Write 1-2 sentences describing {{program_name}}: its phase structure, that it's paced to the client and anchored to measurable change, and that it describes the shape of the work (not a product with a checkout). -->
      <p class="lead muted" style="margin-top:24px;max-width:62ch;">A phased structure, paced to the client and anchored to measurable change. This is the shape of the work, so you know what you're signing up for.</p>

      <div class="spacer-lg"></div>

      <div class="phases" id="phases">
        <!-- AI-GENERATE:journey_phases | Output a JS array of tuples [phase-label, duration-number, duration-detail, phase-name, paragraph] — one per phase of {{program_name}} (typically 3-4). paragraph: 2-4 sentences on what happens that phase. Reference {{method_name}} and {{outcome_measures}} where natural. If the practice has NO structured program, build 3-4 phases describing the general arc of therapy with {{owner_name}}. Replace the placeholder array below. -->
        ${[
          ['Phase 01','30','Days · 1–30','Foundation','Assessment, baseline measures, and stabilization of the most disruptive symptom. We build the working alliance and identify what we are tracking.'],
          ['Phase 02','30','Days · 31–60','Excavation','Pattern identification and values clarification. We name what has been running the show and find out what you actually want instead.'],
          ['Phase 03','30','Days · 61–90','Reconstruction','Behavioral experiments and skills practice. The pace picks up; this is where the change becomes visible to the people around you.'],
          ['Phase 04','30','Days · 91–120','Integration','Relapse prevention, autonomy, and decisions about what comes next. You leave with the structure you needed in the first place.']
        ].map(p=>`
          <div class="phase">
            <span class="pn">${p[0]}</span>
            <div class="days">${p[1]}<small>${p[2]}</small></div>
            <h3>${p[3]}</h3>
            <p>${p[4]}</p>
            <div class="bar"></div>
          </div>`).join('')}
      </div>

      <div class="spacer-lg"></div>

      <div class="two-col">
        <div>
          <span class="sunrise-rule"></span>
          <h2 class="display">What you bring. What I bring.</h2>
        </div>
        <div>
          <!-- AI-GENERATE:journey_reciprocity | Write 2 short paragraphs. P1: what the client brings (honesty, between-session practice, belief that change is possible). P2: what {{owner_name}} brings (evidence-based methods, structured tracking, years of clinical context) and when clients typically see change. Voice: direct, grounded. Each in its own <p>; first <p class="lead muted">. -->
          <p class="lead muted">You bring honesty, the willingness to practice between sessions, and the assumption that change is possible. I bring evidence-based methods, structured tracking, and the steadiness that comes with real clinical experience.</p>
          <p style="margin-top:20px;">Most clients see meaningful change earlier than they expect. The change that holds — the kind that survives a hard week — is the work of the later phases.</p>
          <a class="btn btn-primary" data-route="contact" href="#contact" style="margin-top:32px;">Request a consult to discuss <span class="arrow">→</span></a>
        </div>
      </div>
    </div>
  </section>

  ${contactStrip()}
`;

// ============ FEES ============
routes.fees = () => `
  <section class="tall">
    <div class="wrap">
      <span class="sunrise-rule wide"></span>
      <span class="eyebrow">Fees &amp; Insurance</span>
      <!-- AI-GENERATE:fees_headline | One short display headline (4-8 words) summarizing the practice's billing stance ({{payment_model}}). E.g. for out-of-network: "One fee. No surprises. No insurance billed." Adapt to {{payment_model}}. -->
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:16ch;">One fee. No surprises.</h1>

      <div class="spacer-lg"></div>

      <div class="fees-hero">
        <div class="fee-figure">
          <div class="num"><sup>$</sup>{{session_fee_amount}}</div>
          <div class="per">Per {{session_length}} session · {{payment_model_short}}</div>
          <ul>
            <!-- AI-GENERATE:fees_bullets | Output a JS array of 4-5 short strings describing the practice's billing terms, derived from {{payment_model}}, {{superbill_policy}}, {{cancellation_policy}}, and {{cadence}}. Each <=14 words. Replace the <li> items below. -->
            <li><span>{{payment_model}} — billing handled per the practice's policy</span></li>
            <li><span>{{superbill_policy}}</span></li>
            <li><span>Card on file, charged at session</span></li>
            <li><span>{{cadence}} cadence preferred</span></li>
            <li><span>{{cancellation_policy}}</span></li>
          </ul>
        </div>
        <div>
          <h2 class="display" style="font-size:30px;">Why this model.</h2>
          <!-- AI-GENERATE:fees_why | Write 1 paragraph (3-5 sentences) explaining honestly why {{business_name}} uses its billing model ({{payment_model}}), what the client gets from it, and that a free consult is the way to find out if it's the right fit. If the practice is in-network, explain that instead. Plain, candid, non-defensive. -->
          <p style="margin-top:18px;">A short, honest explanation of why this practice bills the way it does — what it protects about the clinical work, and why a free consult is the best way to find out if it's the right fit for you.</p>
          <div class="crisis-note" style="margin-top:28px;">
            <strong>If this is a mental health emergency,</strong> call or text <strong>988</strong> or call <strong>911</strong>. This site is not a crisis service.
          </div>
        </div>
      </div>

      <div class="spacer-lg"></div>

      <span class="sunrise-rule"></span>
      <h2 class="display" style="margin-bottom:24px;">Frequently asked.</h2>
      <div class="faq">
        <!-- AI-GENERATE:fees_faq | Output a JS array of 4-6 tuples [question, answer]. Cover: what the billing model means for the client's wallet ({{payment_model}}), whether insurance is billed, sliding-scale availability ({{sliding_scale_policy}}), typical length of therapy (reference {{program_name}}), and fit ("are you a good fit for me?" — name {{service_areas}} eligibility and any populations referred out). Answers: plain, specific, honest. Replace the placeholder array below. -->
        ${[
          ['What does your billing model mean for my wallet?',
           'Replace with a plain-language explanation of {{payment_model}} and what the client can expect to pay or be reimbursed.'],
          ['Will you bill my insurance for me?', 'Replace with the practice\'s actual answer based on {{payment_model}}.'],
          ['Do you offer a sliding scale?',
           'Replace with {{sliding_scale_policy}}.'],
          ['How long do clients usually stay in therapy?',
           'Replace with a short, honest answer that references {{program_name}} as one structured path.'],
          ['Are you a good fit for me?',
           'Replace with who is and isn\'t a good fit — name {{service_areas}} eligibility and any conditions referred to specialists.']
        ].map(f=>`
          <div class="faq-item">
            <div class="q"><span>${f[0]}</span><span class="plus" aria-hidden="true"></span></div>
            <div class="a"><div style="padding-bottom:8px;">${f[1]}</div></div>
          </div>`).join('')}
      </div>
    </div>
  </section>

  ${contactStrip()}
`;

// ============ WRITING ============
routes.writing = () => `
  <section class="tall">
    <div class="wrap">
      <span class="sunrise-rule wide"></span>
      <span class="eyebrow">Writing</span>
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:16ch;">Field notes from the practice.</h1>
      <!-- AI-GENERATE:writing_intro | Write 1-2 sentences introducing {{owner_name}}'s writing: essays on clinical work, frameworks, and the mechanics of change, written for the prospective client. Plain, inviting. -->
      <p class="lead muted" style="margin-top:24px;max-width:62ch;">Essays on clinical work, frameworks, and the unglamorous mechanics of change — written for the client who wants to understand what's actually happening in the room.</p>

      <div class="spacer-md"></div>

      <div class="populations" style="margin-bottom:36px;">
        <!-- AI-GENERATE:writing_tags | Output a JS array of 5-7 short topic-filter labels (keep "All" first). Derive from {{method_name}}, {{program_name}}, {{specialties}} and the post tags. Replace the array below. -->
        ${['All','Tag two','Tag three','Tag four','Tag five','Tag six'].map((t,i)=>`<span class="chip" ${i===0?'style="border-color:var(--ink);"':''}><span class="dot"></span>${t}</span>`).join('')}
      </div>

      ${postCards(posts, {tag:true})}
    </div>
  </section>
  ${contactStrip()}
`;

// ============ CONTACT ============
routes.contact = () => `
  <section class="tall">
    <div class="wrap">
      <span class="sunrise-rule wide"></span>
      <span class="eyebrow">Contact</span>
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:16ch;">Request a consult.</h1>
      <!-- AI-GENERATE:contact_intro | Write 1-2 sentences inviting the visitor to send a short message; state the response time ({{response_time}}) and that it leads to a free {{consult_length}} consult to check fit. Warm, low-pressure. -->
      <p class="lead muted" style="margin-top:24px;max-width:62ch;">Send a short message and {{owner_first_name}} will reply {{response_time}} to schedule a free {{consult_length}} consult — for both of us to see if we're a fit.</p>

      <div class="spacer-lg"></div>

      <div class="two-col" style="grid-template-columns:1fr 1fr;">
        <div>
          ${formMarkup()}
        </div>
        <div>
          <div class="card" style="padding:32px 30px;">
            <span class="eyebrow">Direct</span>
            <p style="margin-top:14px;font-family:'Fraunces',serif;font-size:22px;font-weight:460;line-height:1.35;">If you'd rather not use the form, email {{owner_first_name}} directly.</p>
            <p class="mono" style="margin-top:14px;font-size:14px;color:var(--ink);">{{email}}</p>
            <p class="mono" style="margin-top:8px;font-size:14px;color:var(--ink);">{{phone}}</p>
            <hr class="divider" style="margin:24px 0;"/>
            <span class="eyebrow">Office</span>
            <p style="margin-top:8px;font-size:14.5px;line-height:1.6;">{{business_name}}<br/>{{address_line1}}<br/>{{address_line2}}</p>
            <hr class="divider" style="margin:24px 0;"/>
            <span class="eyebrow">Telehealth</span>
            <p style="margin-top:8px;font-size:14.5px;">Available across {{service_areas}}. Sessions held on a HIPAA-compliant video platform.</p>
          </div>
        </div>
      </div>
    </div>
  </section>
`;

// ============ PRIVACY (combined privacy/terms/a11y) ============
routes.privacy = () => `
  <section class="tall">
    <div class="wrap" style="max-width:780px;">
      <span class="sunrise-rule wide"></span>
      <span class="eyebrow">Privacy · Terms · Accessibility</span>
      <h1 class="display" style="margin-top:14px;font-size:clamp(36px,4.6vw,56px);">This website does not collect or store protected health information.</h1>

      <div class="spacer-md"></div>

      <!-- NOTE: This Privacy / Terms / Accessibility copy is general boilerplate. Have the practice's counsel review before publishing. Tokens below pull contact + jurisdiction from practice.md. -->
      <h2 class="display" style="font-size:24px;">Privacy</h2>
      <p style="margin-top:12px;">${INQUIRY_ENDPOINT
        ? `The contact form delivers your message privately to {{owner_first_name}}'s practice inbox so {{owner_first_name}} can reply. Messages are kept for that purpose only — they are never published, shared, or used for marketing. Please do not include detailed clinical information in the form.`
        : `This site has no contact form — reaching out happens directly by email or phone, so this website stores nothing you send.`} There are no user accounts, no analytics that fingerprint users, and no third-party tracking pixels. Fonts load from Google Fonts; no marketing trackers run on this site.</p>
      <p style="margin-top:12px;">Clinical care, once underway, is governed by HIPAA and is documented in a HIPAA-compliant electronic record system separate from this website. Notice of Privacy Practices is provided to all clients at intake.</p>

      <div class="spacer-md"></div>
      <h2 class="display" style="font-size:24px;">Terms</h2>
      <p style="margin-top:12px;">Information on this site is general and does not constitute medical or psychotherapeutic advice. Visiting this site or submitting the consult form does not create a clinician-client relationship. A clinician-client relationship is established only after a signed informed-consent agreement at the start of clinical care.</p>

      <div class="spacer-md"></div>
      <h2 class="display" style="font-size:24px;">Accessibility</h2>
      <p style="margin-top:12px;">This site targets WCAG 2.2 AA. All interactive elements are keyboard navigable with visible focus rings. Motion respects <span class="mono" style="font-size:13px;">prefers-reduced-motion</span>. Type contrast is verified at every text/background pairing. If you encounter an accessibility issue, please email {{email}} and it will be addressed.</p>

      <div class="spacer-md"></div>
      <div class="crisis-note">
        <strong>If you are in crisis:</strong> Call or text <strong>988</strong> · Call <strong>911</strong> for an emergency · {{crisis_line_1_label}} <strong>{{crisis_line_1_number}}</strong> · {{crisis_line_2_label}} <strong>{{crisis_line_2_number}}</strong>.
      </div>
    </div>
  </section>
`;

// ============ HELPERS ============
// Writing cards — the truth rules:
//   * a card is a LINK only when a real page exists (p.href, written by the
//     publisher when an approved essay goes live); otherwise it renders as a
//     non-navigating preview — never an anchor to a 404.
//   * dates and reading times are shown only when present (the publisher
//     stamps real values); nothing here invents them.
//   * zero posts renders an honest "first essays are on the way" state
//     instead of a fake library.
function postCards(list, opts){
  const withTag = !!(opts && opts.tag);
  if(!list.length){
    return `
        <div class="card posts-empty" style="padding:32px 30px;">
          <span class="eyebrow">Coming soon</span>
          <p class="lead muted" style="margin-top:12px;">The first essays are being written. Every piece is reviewed and approved by {{owner_first_name}} before it appears here.</p>
        </div>`;
  }
  return `
      <div class="posts-grid">
        ${list.map(p=>{
          const meta = [p.date, p.readingTime, withTag ? p.tag : ''].filter(Boolean)
            .map(x=>`<span>${x}</span>`).join('');
          const body = `
            <div class="meta">${meta}</div>
            <h3>${p.title}</h3>
            <p>${p.description}</p>
            ${p.href ? '<span class="read">Read essay <span class="arrow">→</span></span>' : ''}`;
          return p.href
            ? `<a class="post-card" href="${p.href}" data-slug="${p.slug}">${body}</a>`
            : `<article class="post-card" data-slug="${p.slug}">${body}</article>`;
        }).join('')}
      </div>`;
}

function contactStrip(){
  return `
  <section class="contact-strip">
    <div class="contact-grid">
      <div>
        <span class="sunrise-rule wide"></span>
        <h2 class="display">When you're ready, the next move is small.</h2>
        <p class="lead muted" style="margin-top:18px;">A short message. A free {{consult_length}} call. From there, we decide together.</p>
        <div style="margin-top:32px;display:flex;gap:14px;flex-wrap:wrap;">
          <span class="chip"><span class="dot"></span>Free {{consult_length}} consult</span>
          <span class="chip"><span class="dot"></span>{{response_time}}</span>
          <span class="chip"><span class="dot"></span>{{service_areas}} telehealth</span>
        </div>
      </div>
      <div>
        ${formMarkup()}
      </div>
    </div>
  </section>`;
}

function formMarkup(){
  // No live delivery endpoint wired at build time → no form. A form whose
  // submissions go nowhere would be a lie; the honest fallback is a direct
  // email/phone card, so every message reaches a real inbox.
  if(!INQUIRY_ENDPOINT){
    return `
  <div class="card consult-direct" style="padding:32px 30px;">
    <span class="eyebrow">Get in touch</span>
    <p style="margin-top:14px;font-family:'Fraunces',serif;font-size:22px;font-weight:460;line-height:1.35;">Email or call {{owner_first_name}} directly — a short note is plenty.</p>
    <p class="mono" style="margin-top:14px;font-size:14px;color:var(--ink);">{{email}}</p>
    <p class="mono" style="margin-top:8px;font-size:14px;color:var(--ink);">{{phone}}</p>
    <div class="crisis-note" style="margin-top:24px;">
      <strong>If this is a mental health emergency,</strong> call or text <strong>988</strong>, or call <strong>911</strong>.
    </div>
  </div>
  `;
  }
  return `
  <form class="consult-form" novalidate>
    <div class="crisis-note">
      <strong>This form is for general inquiries only.</strong> Please do not include detailed clinical information. If this is a mental health emergency, call or text <strong>988</strong>, or call <strong>911</strong>.
    </div>
    <div class="row-2">
      <div class="field">
        <label for="cf-name">Name</label>
        <input id="cf-name" name="name" type="text" required autocomplete="name" />
      </div>
      <div class="field">
        <label for="cf-email">Email</label>
        <input id="cf-email" name="email" type="email" required autocomplete="email" />
      </div>
    </div>
    <div class="row-2">
      <div class="field">
        <label for="cf-phone">Phone (optional)</label>
        <input id="cf-phone" name="phone" type="tel" autocomplete="tel" />
      </div>
      <div class="field">
        <label for="cf-state">{{location_field_label}}</label>
        <select id="cf-state" name="state" required>
          <option value="">Select…</option>
          <!-- AI-GENERATE:state_options | Output one <option>…</option> per jurisdiction the practice serves (from {{service_areas}}), followed by an <option>Other</option>. Replace the two placeholder options below. -->
          <option>Service area one</option>
          <option>Service area two</option>
          <option>Other</option>
        </select>
      </div>
    </div>
    <div class="field">
      <label for="cf-notes">What brings you in?</label>
      <textarea id="cf-notes" name="notes" maxlength="500" placeholder="A sentence or two is fine."></textarea>
    </div>
    <div class="honeypot" aria-hidden="true">
      <label>Leave this field empty<input name="website" tabindex="-1" autocomplete="off" /></label>
    </div>
    <button class="btn btn-primary" type="submit" style="width:100%;justify-content:center;margin-top:8px;">Send message <span class="arrow">→</span></button>
    <div class="form-foot">Your message is delivered privately to {{owner_first_name}}'s practice inbox and is never published on this site.</div>
  </form>
  `;
}

// ============ DATA ============
// Inquiry delivery endpoint — wired at build time by the engine (pipeline.py
// composes it from the office service's public origin + this site's slug; the
// office stores each message and surfaces it in the practice's staff inbox).
// Empty string = no live endpoint: the template renders a direct-contact card
// instead of a form, so a message can never be silently dropped.
const INQUIRY_ENDPOINT = '{{inquiry_endpoint}}';

// AI-GENERATE:blog_posts | Output the JS posts array for {{business_name}}'s "Writing" section.
//   HONESTY CONTRACT: at build time NO essays exist yet, so the emitted array MUST be empty —
//   never invent titles, dates, or reading times for pages that were never written. The
//   publisher prepends a real entry {slug, title, description, date, readingTime, tag, href}
//   each time an approved essay goes live (real date, reading time computed from word count,
//   working href). Cards without an href render as non-navigating previews; an empty array
//   renders an honest "first essays are on the way" state. Replace the placeholder array below.
const posts = [
  {
    slug:'post-one',
    title:'First essay title goes here',
    description:'A one-to-two sentence summary of the first essay, in the clinician\'s voice.',
    date:'Mon 01, 2026', readingTime:'6 min read', tag:'Topic'
  },
  {
    slug:'post-two',
    title:'Second essay title goes here',
    description:'A one-to-two sentence summary of the second essay, in the clinician\'s voice.',
    date:'Mon 02, 2026', readingTime:'8 min read', tag:'Topic'
  },
  {
    slug:'post-three',
    title:'Third essay title goes here',
    description:'A one-to-two sentence summary of the third essay, in the clinician\'s voice.',
    date:'Mon 03, 2026', readingTime:'5 min read', tag:'Topic'
  }
];

// ============ ROUTER ============
function navigate(name, push){
  const ids = ['home','about','approach','method','journey','who','fees','writing','contact','privacy'];
  ids.forEach(id => {
    const el = document.getElementById('route-' + id);
    if(!el) return;
    if(id === name){
      el.hidden = false;
      el.innerHTML = (routes[name] || routes.home)();
    } else {
      el.hidden = true;
      el.innerHTML = '';
    }
  });
  // active nav
  document.querySelectorAll('.nav-links a').forEach(a => {
    a.classList.toggle('active', a.dataset.route === name);
  });
  // scroll
  window.scrollTo({ top:0, behavior:'instant' in window ? 'instant' : 'auto' });
  // wire reveals + interactives
  setTimeout(()=>{
    initReveals();
    initFAQ();
    initForm();
    initPhases();
    initHeroVideo();
  }, 30);
  // history: push a real entry on user navigation so Back/Forward steps through
  // sections; replace on initial load + hashchange so we never duplicate entries.
  const _url = '#' + name;
  if(push){ history.pushState({route:name}, '', _url); }
  else { history.replaceState({route:name}, '', _url); }
}

// ============ INTERACTIONS ============
function initReveals(){
  const els = document.querySelectorAll('.reveal');
  if(!('IntersectionObserver' in window)){ els.forEach(e=>e.classList.add('in')); return; }
  const io = new IntersectionObserver(entries=>{
    entries.forEach(en=>{
      if(en.isIntersecting){ en.target.classList.add('in'); io.unobserve(en.target); }
    });
  }, { threshold: 0.12 });
  els.forEach(e=>io.observe(e));
}
function initFAQ(){
  document.querySelectorAll('.faq-item').forEach(item=>{
    item.addEventListener('click', ()=> item.classList.toggle('open'));
  });
}
function initForm(){
  document.querySelectorAll('.consult-form').forEach(form=>{
    form.addEventListener('submit', async e=>{
      e.preventDefault();
      const data = new FormData(form);
      if(data.get('website')) return; // honeypot
      const name = (data.get('name')||'').toString().trim();
      const email = (data.get('email')||'').toString().trim();
      const state = (data.get('state')||'').toString();
      if(!name || !email || !state){
        form.querySelectorAll('input, select').forEach(i=>{
          if(i.required && !i.value) i.style.borderColor = '#B45A3A';
        });
        return;
      }
      // Deliver for real: POST to the office service, which stores the
      // message and surfaces it in {{owner_first_name}}'s staff inbox.
      // Success is only claimed when the service confirmed receipt; a
      // failure says so honestly and points at direct email/phone.
      const btn = form.querySelector('button[type="submit"]');
      const btnHTML = btn ? btn.innerHTML : '';
      if(btn){ btn.disabled = true; btn.textContent = 'Sending…'; }
      let delivered = false;
      try{
        const res = await fetch(INQUIRY_ENDPOINT, {
          method:'POST',
          headers:{ 'Content-Type':'application/json' },
          body: JSON.stringify({
            name, email, state,
            phone: (data.get('phone')||'').toString().trim(),
            notes: (data.get('notes')||'').toString().trim(),
            website: ''
          })
        });
        delivered = res.ok;
      } catch(_){ delivered = false; }
      const firstName = name.split(' ')[0].replace(/[<>&"']/g,'');
      const msg = document.createElement('div');
      msg.className = 'success';
      if(delivered){
        msg.innerHTML = `<strong>Thank you, ${firstName}.</strong>Your message is in {{owner_first_name}}'s inbox. {{owner_first_name}} will reply {{response_time}}. If this is urgent, please call {{phone}}. If this is a crisis, call or text 988.`;
        form.replaceWith(msg);
        return;
      }
      if(btn){ btn.disabled = false; btn.innerHTML = btnHTML; }
      msg.style.background = '#FBF3EE';
      msg.style.borderColor = 'rgba(180,90,58,0.35)';
      msg.innerHTML = `<strong>Your message could not be sent.</strong>Nothing was delivered — please email {{email}} or call {{phone}} directly. If this is a crisis, call or text 988.`;
      const prev = form.parentElement ? form.parentElement.querySelector('.form-send-error') : null;
      if(prev) prev.remove();
      msg.classList.add('form-send-error');
      form.insertAdjacentElement('beforebegin', msg);
    });
  });
}
function initPhases(){
  const phases = document.querySelectorAll('#phases .phase');
  if(!phases.length) return;
  if(!('IntersectionObserver' in window)){ phases.forEach(p=>p.classList.add('in')); return; }
  const io = new IntersectionObserver(entries=>{
    entries.forEach(en=>{
      if(en.isIntersecting){
        const idx = [...phases].indexOf(en.target);
        setTimeout(()=> en.target.classList.add('in'), idx * 220);
        io.unobserve(en.target);
      }
    });
  }, { threshold: 0.3 });
  phases.forEach(p=>io.observe(p));
}

// ============ HERO VIDEO (blob-URL workaround) ============
// The sandbox CDN doesn't advertise Accept-Ranges, which Chromium's <video>
// pipeline needs for MP4 even when the whole body is reachable. Fetch the
// file as a Blob, hand the element an object-URL, and the native player
// treats it as a fully-loaded local source. The static .hawks-fallback
// plate sits behind it as a graceful fallback if anything goes wrong.
let _heroVideoStarted = false;
async function initHeroVideo(){
  if(_heroVideoStarted) return;
  const v = document.querySelector('.hawks-video');
  if(!v) return;
  // Prefer the bundled blob URL (standalone export) over the data-src path (dev)
  const url = (window.__resources && window.__resources.hawksVideo) || v.dataset.src;
  if(!url) return;
  _heroVideoStarted = true;
  try{
    const res = await fetch(url);
    if(!res.ok) throw new Error('fetch ' + res.status);
    const blob = await res.blob();
    const obj = URL.createObjectURL(blob);
    v.src = obj;
    v.load();
    v.play().catch(()=>{ /* autoplay blocked — silent */ });
  } catch(e){
    // Leave the static fallback visible
    v.remove();
  }
}

// ============ MOBILE NAV (disclosure menu ≤880px) ============
// Below the breakpoint the inline links collapse behind a hamburger; without
// this, phones had no navigation at all. Guarded lookups: in non-browser
// shims (render_check) the elements are absent and this no-ops.
function setNavOpen(open){
  const wrap = document.querySelector('.nav-wrap');
  const btn = document.querySelector('.nav-toggle');
  if(!wrap || !btn) return;
  wrap.classList.toggle('nav-open', open);
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  btn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
}
function initNavToggle(){
  const btn = document.querySelector('.nav-toggle');
  const wrap = document.querySelector('.nav-wrap');
  if(!btn || !wrap) return;
  btn.addEventListener('click', ()=>{
    setNavOpen(!wrap.classList.contains('nav-open'));
  });
  document.addEventListener('keydown', e=>{
    if(e.key === 'Escape' && wrap.classList.contains('nav-open')){
      setNavOpen(false);
      btn.focus && btn.focus();
    }
  });
}
initNavToggle();

// ============ CLICK DELEGATION FOR data-route ============
document.addEventListener('click', e=>{
  const t = e.target.closest('[data-route]');
  if(!t) return;
  e.preventDefault();
  setNavOpen(false); // picking a destination closes the mobile menu
  navigate(t.dataset.route, true);
});

// Back/Forward + manual hash edits: re-render to match the URL without adding a
// new entry. pushState/replaceState don't fire hashchange, so our own
// navigations never double-trigger this.
window.addEventListener('hashchange', ()=>{
  const r = (location.hash || '').replace('#','');
  if(r && !routes[r]) return;   // in-page anchor (e.g. #main skip link) — leave it native
  navigate(r || 'home', false);
});

// initial
const initial = (location.hash || '').replace('#','') || 'home';
navigate(routes[initial] ? initial : 'home', false);
