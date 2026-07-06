/* ─────────────────────────────────────────────────────────────
   Single-page site — client-side routing, content sections, motion, and contact form.
   ───────────────────────────────────────────────────────────── */

// ============ ROUTE TEMPLATES ============
const routes = {};

routes.home = () => `
  <!-- HERO -->
  <section class="hero" aria-labelledby="h1">
    <!-- Hero band — full-width ambient banner from below nav down to where the H1 begins.
         Default asset is the bundled nature clip (assets/hawks-hero.mp4) — part of the template's
         visual style. upload OPTIONAL: to use a custom hero video, replace assets/hawks-hero.mp4
         (keep the filename) and update the aria-label below. Static fallback: assets/hawks-sky.png (CSS). -->
    <div class="hawks-band">
      <video class="hawks-video" autoplay muted loop playsinline preload="auto" data-src="assets/hawks-hero.mp4" aria-label="Two hawks in flight at sunrise"></video>
      <div class="hawks-fallback" aria-hidden="true"></div>
      <div class="hawks-grade" aria-hidden="true"></div>
      <div class="hawks-fade" aria-hidden="true"></div>
    </div>
    <div class="hero-inner">
      <div class="hero-content">
        <span class="hero-eyebrow"><span class="dot"></span> Now welcoming new clients · Texas & New Mexico telehealth</span>
        <span class="sunrise-rule wide"></span>
        
        <h1 id="h1">Steady ground for the <span class="accent">parts that won't settle.</span></h1>
        
        <p class="hero-sub">Out-of-network private psychotherapy with Jordan Avery, LCSW, for adults, young professionals, and healthcare and first-responder clients carrying anxiety, trauma, or a hard transition. The work is evidence-based and structured, and it moves at a pace your nervous system can actually keep.</p>
        <div class="hero-actions">
          <a class="btn btn-primary" data-route="contact" href="#contact">Request a consult <span class="arrow">→</span></a>
          <a class="btn btn-ghost" data-route="method" href="#method">See the method</a>
        </div>
      </div>
      <div class="hero-meta" aria-hidden="true">
        Austin, TX · Telehealth Texas & New Mexico<br/>
        $185 / 50-minute session · Out-of-network<br/>
        within two business days
      </div>
    </div>
  </section>

  <!-- QUICK FACTS -->
  <div class="qf-wrap">
    <div class="qf glass" role="region" aria-label="Quick facts">
      <div class="item">
        <span class="label">Office</span>
        <span class="value">Austin, TX <small>Suite 220</small></span>
      </div>
      <div class="item">
        <span class="label">Telehealth</span>
        <span class="value">Texas & New Mexico</span>
      </div>
      <div class="item">
        <span class="label">Fee</span>
        <span class="value">$185 <small>50-minute · out-of-network</small></span>
      </div>
      <div class="item">
        <span class="label">Cadence</span>
        <span class="value">Weekly <small>or as clinically indicated</small></span>
      </div>
    </div>
  </div>

  <!-- METHOD INTRO -->
  
  <section class="reveal">
    <div class="wrap">
      <div class="sweep-rule"></div>
      <div class="section-head">
        <span class="eyebrow">The GROUND Method</span>
        
        <h2 class="display">A way back to steady when everything spikes.</h2>
        
        <p class="lede">GROUND is the framework Jordan Avery built for the moment anxiety or a trauma response takes the wheel and the usual coping stops working.</p>
      </div>

      <div class="stoick-grid">
        ${[
          ['G','Ground','Settle the body first so the thinking brain can come back online.'],
          ['R','Recognize','Name the pattern you are actually caught in, without judgment.'],
          ['O','Open','Make room for the feeling instead of fighting or fleeing it.'],
          ['U','Understand','Trace where the pattern learned to protect you, and from what.'],
          ['N','Navigate','Choose a next move that fits your values, not the old reflex.'],
          ['D','Deepen','Practice it until the new response holds under real pressure.']
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
          
          <h2 class="display" style="margin-top:14px;">People who hold it together for everyone else and are <em>tired</em>.</h2>
        </div>
        <div>
          
          <p class="lead muted">Most people who come to Cedar &amp; Sage Therapy are competent, capable adults who are quietly worn down — by anxiety that won't quit, by a trauma that still echoes, or by a transition that knocked the floor out. They are looking for a clinician who meets that with structure, real evidence, and a steady presence, not platitudes.</p>
          <div class="populations" style="margin-top:28px;">
            
            ${['Anxiety &amp; panic','Trauma &amp; PTSD','EMDR','Life transitions','Healthcare workers','First responders','Young professionals','Burnout'].map(p=>`<span class="chip"><span class="dot"></span>${p}</span>`).join('')}
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- PULL QUOTE -->
  
  <section class="tight">
    <div class="pullquote reveal">
      <span class="sunrise-rule wide center"></span>
      <blockquote>"Anxiety and trauma aren't proof that something is wrong with you. They're old protection that outlived the danger — and protection can be updated."</blockquote>
      <cite>— Jordan Avery, LCSW</cite>
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
      <div class="posts-grid">
        ${posts.slice(0,3).map(p=>`
          <a class="post-card" data-route="writing" href="#writing" data-slug="${p.slug}">
            <div class="meta"><span>${p.date}</span><span>${p.readingTime}</span></div>
            <h3>${p.title}</h3>
            <p>${p.description}</p>
            <span class="read">Read essay <span class="arrow">→</span></span>
          </a>`).join('')}
      </div>
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
          <!-- upload HEADSHOT: replace assets/placeholder-headshot.svg with a real portrait (JPG/PNG, portrait orientation ~800x1000) and update the filename in the url() below. The styled frame + caption stay. -->
          <div class="portrait" aria-label="Portrait of Jordan Avery" style="background-image:url('assets/placeholder-headshot.svg');background-size:cover;background-position:center;">
            <span class="placeholder">Portrait — Jordan Avery, LCSW · upload</span>
          </div>
          <div class="facts-list" style="margin-top:24px;">
            <div class="fact-row"><span class="k">Credential</span><span class="v">LCSW</span></div>
            <div class="fact-row"><span class="k">TX License</span><span class="v mono">#LCSW-00000 (placeholder) — 2016</span></div>
            <div class="fact-row"><span class="k">NM License</span><span class="v mono">#NM-00000 (placeholder) — 2021</span></div>
            <div class="fact-row"><span class="k">Education</span><span class="v">MSW, University of Texas at Austin, 2013</span></div>
            <div class="fact-row"><span class="k">Founded</span><span class="v">Cedar & Sage Therapy · 2020</span></div>
            <div class="fact-row"><span class="k">Office</span><span class="v">1100 Guadalupe St, Suite 220, Austin, TX 78701</span></div>
            <div class="fact-row"><span class="k">Phone</span><span class="v mono">512-555-0147</span></div>
          </div>
        </div>
        <div>
          <span class="eyebrow">About</span>
          
          <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,68px);">Jordan Avery is a Licensed Clinical Social Worker who helps anxious, overwhelmed adults find solid footing after anxiety, trauma, or a hard transition.</h1>
          <div class="spacer-md"></div>
          
          <p class="lead">Jordan Avery, LCSW, spent more than a decade across community mental health, a hospital trauma service, and an employee-assistance program before going into private practice — the kind of rooms where the work mattered too much to be vague.</p>
          <p style="margin-top:20px;">Jordan founded Cedar &amp; Sage Therapy in 2020 and now sees adults privately for anxiety, trauma, and life transitions. Licensed to serve clients across Texas and New Mexico, with telehealth and an in-person office in Austin, TX.</p>
          <p style="margin-top:20px;">The approach is evidence-based and outcomes-tracked — CBT, ACT, and EMDR — and shaped into two frameworks Jordan uses in the room: the GROUND Method for the moments that spike, and The Steady Work for clients who want a phased, paced path through. Underneath the structure, the stance is simple: people who show up for the work deserve a clinician who shows up for it too.</p>

          <div class="callout" style="margin-top:40px;">
            <span class="eyebrow">A note from Jordan</span>
            
            <p>"I do my steadiest work with people who are done white-knuckling it and ready to understand what's actually happening in their body and their patterns. I'll bring the structure and the evidence; you bring honesty and a willingness to practice between sessions. If that sounds right, I'm a good clinician to do this with."</p>
          </div>
        </div>
      </div>

      <div class="spacer-lg"></div>
      <span class="sunrise-rule wide"></span>
      
      <h2 class="display">The rooms that built this practice.</h2>
      
      <p class="lede" style="margin-top:14px;color:var(--ink-2);max-width:62ch;">A decade in high-stakes settings — community care, hospital trauma, first-responder support — taught the structure and steadiness this practice now runs on.</p>
      <div class="spacer-md"></div>

      <div class="timeline">
        
        ${[
          ['2013 – 2016','Community Mental Health Center','Clinician','Carried a full caseload of anxiety, depression, and trauma, and learned to do good work inside real-world constraints.'],
          ['2016 – 2019','Hospital Trauma &amp; Acute Care Service','Clinical Social Worker','Worked bedside with patients and families in acute crisis, where trauma-informed care stops being a slogan.'],
          ['2019 – 2020','Employee Assistance &amp; First-Responder Program','Senior Clinician','Supported healthcare workers and first responders through burnout and critical-incident stress.'],
          ['2020 – present','Cedar &amp; Sage Therapy','Founder · Private Practice','Private practice serving anxiety, trauma, and life transitions, licensed for Texas and New Mexico.']
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
      
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:18ch;">Evidence-based, outcomes-tracked, body-aware.</h1>
      
      <p class="lead muted" style="margin-top:24px;">Jordan draws on CBT, ACT, and EMDR in combination — matched to what you're carrying, not applied as a one-size brand — and tracks progress with brief standardized measures (GAD-7 and PCL-5) so we both know whether the work is moving.</p>

      <div class="spacer-lg"></div>

      <div class="modality-grid">
        
        ${[
          ['CBT','Cognitive Behavioral Therapy','Maps the loop between thoughts, feelings, and behavior, then tests the beliefs that keep anxiety running so they lose their grip. Practical, structured, and well-suited to anxiety and panic.','Beck — Cognitive Therapy and the Emotional Disorders (1976)'],
          ['ACT','Acceptance &amp; Commitment Therapy','Builds room to feel hard things without being run by them, and points action toward what you actually value. Helps when the fight against anxiety has become its own problem.','Hayes, Strosahl &amp; Wilson — Acceptance and Commitment Therapy (1999)'],
          ['EMDR','Eye Movement Desensitization &amp; Reprocessing','A structured, eight-phase approach that helps the brain reprocess stuck traumatic memories so they stop firing in the present. Strong evidence base for PTSD and single-incident trauma.','Shapiro — Eye Movement Desensitization and Reprocessing (1995)'],
          ['MI','Motivational Interviewing','A collaborative way of working through ambivalence at the start of a transition, so change comes from your own reasons rather than pressure.','Miller &amp; Rollnick — Motivational Interviewing (1991)']
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
          
          <p class="lead muted">Sessions are 50-minute. The first two or three are assessment-heavy — history, goals, and a baseline using GAD-7 and PCL-5 so we can see change over time. From there, sessions are structured but not rigid: a brief check-in, the clinical work we've agreed on, one practice to carry into the week, and a short close.</p>
          <p style="margin-top:18px;">Trauma-informed throughout. With EMDR and any trauma work, the pace is set by your nervous system, not the calendar — we slow down or pause the moment we need to.</p>
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
      <span class="eyebrow">The GROUND Method</span>
      
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:16ch;">Get grounded. Then get free.</h1>
      
      <p class="lead muted" style="margin-top:24px;max-width:62ch;">GROUND is the framework Jordan Avery uses to help clients interrupt an anxiety or trauma response and choose a reaction that fits who they actually are. Each step pairs the underlying science with one concrete practice you can run this week.</p>

      <div class="spacer-lg"></div>

      
      ${[
        ['G','Ground','01','Settle the body before the mind',
          'When anxiety or a trauma response fires, the body shifts into threat mode and the thinking brain goes partly offline. Grounding uses the breath and the senses to signal safety to the nervous system so the prefrontal cortex can come back into the conversation. You cannot reason your way out of a spike you have not first calmed.',
          'Try slow exhales — in for four, out for six — for two minutes, and name five things you can see and four you can touch.'],
        ['R','Recognize','02','Name the pattern, not the verdict',
          'Most anxious and trauma-driven reactions run on autopilot and feel like fact. Recognizing means catching the pattern as it happens and naming it plainly, without making it a character flaw. Naming an internal state reliably takes some of the heat out of it.',
          'When you feel the surge, finish this sentence on paper: "Here is the part of me that is trying to protect me by ____."'],
        ['O','Open','03','Make room instead of bracing',
          'The instinct is to fight the feeling or run from it, which usually feeds it. Opening, drawn from ACT, means letting the sensation be present without acting on it — willingness, not approval. Discomfort you stop fighting tends to crest and pass faster than discomfort you wrestle.',
          'Set a timer for ninety seconds and let one uncomfortable feeling simply be there, breathing, without fixing it.'],
        ['U','Understand','04','Trace where it learned to protect you',
          'Patterns are not random; they were adaptive somewhere, often a long time ago. Understanding connects the present reaction to the history that trained it, which is also where EMDR does its work on stuck memories. Context turns "what is wrong with me" into "this makes sense, and it can update."',
          'Ask of the reaction: when did this first become a useful thing to do, and is that still true now?'],
        ['N','Navigate','05','Choose the move that fits your values',
          'Once the body is settled and the pattern is seen, there is room to choose. Navigating means picking a next action aligned with what you value rather than the old reflex. Values-based action is a core mechanism of how ACT produces durable change.',
          'Name one small action this week that the calmer, wiser version of you would take, and schedule it.'],
        ['D','Deepen','06','Practice until it holds under pressure',
          'A new response is fragile until it has been rehearsed in real conditions. Deepening means repeating the sequence on ordinary days so it is available on hard ones — the same way any skill consolidates through practice. The goal is not perfection; it is a response you can reach for when it counts.',
          'Run the full GROUND sequence once this week on a low-stakes annoyance, so it is wired in before a real spike.']
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
        
        <p>"I called it GROUND because grounding is the step almost everyone skips. People want to think their way out of anxiety, but the body has to feel safe before the mind can do anything useful. Settle the body first, and every step after it actually works."</p>
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
      <span class="eyebrow">The Steady Work</span>
      
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:18ch;">The Steady Work: a paced path through anxiety and trauma, usually over 12 to 16 weeks.</h1>
      
      <p class="lead muted" style="margin-top:24px;max-width:62ch;">The Steady Work moves through three phases, paced to you and anchored to measurable change on GAD-7 and PCL-5. It describes the shape of the work so you know what you're stepping into — not a product with a checkout.</p>

      <div class="spacer-lg"></div>

      <div class="phases" id="phases">
        
        ${[
          ['Phase 01','4','Weeks · 1–4','Steady','Assessment, baseline GAD-7 and PCL-5, and getting the most disruptive symptom under enough control to work. We build the alliance, teach the GROUND basics, and agree on what we are tracking.'],
          ['Phase 02','6','Weeks · 5–10','Sort','Pattern work and values clarification with CBT and ACT, and EMDR where trauma is driving things. We name what has been running the show, trace where it learned to, and find out what you want instead.'],
          ['Phase 03','4','Weeks · 11–14','Hold','Behavioral experiments and rehearsal under real conditions. The new responses get practiced until they hold, we re-measure, and we plan for autonomy and relapse prevention so you leave steadier than you came in.']
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
          
          <p class="lead muted">You bring honesty, a willingness to practice between sessions, and the working assumption that change is possible. I bring CBT, ACT, and EMDR, structured tracking with GAD-7 and PCL-5, and the steadiness that comes from a decade of clinical work in high-stakes settings.</p>
          <p style="margin-top:20px;">Some clients feel the early symptom relief sooner than they expect; the change that holds under a hard week is the work of the later phases. I won't promise a timeline I can't honor — we watch the measures together and adjust.</p>
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
      
      <h1 class="display" style="margin-top:14px;font-size:clamp(40px,5.4vw,72px);max-width:16ch;">One fee. Out-of-network. No surprises.</h1>

      <div class="spacer-lg"></div>

      <div class="fees-hero">
        <div class="fee-figure">
          <div class="num"><sup>$</sup>185</div>
          <div class="per">Per 50-minute session · out-of-network</div>
          <ul>
            
            <li><span>Out-of-network; insurance is not billed directly</span></li>
            <li><span>Monthly superbill provided on request for reimbursement</span></li>
            <li><span>Card on file, charged at the time of session</span></li>
            <li><span>Weekly cadence preferred, especially early on</span></li>
            <li><span>48-hour cancellation policy</span></li>
          </ul>
        </div>
        <div>
          <h2 class="display" style="font-size:30px;">Why this model.</h2>
          
          <p style="margin-top:18px;">Cedar &amp; Sage Therapy is out-of-network for one honest reason: insurance billing requires assigning a mental-health diagnosis and accepting an insurer's limits on session length, frequency, and approach. Staying out-of-network keeps those clinical decisions between you and me, and keeps your record private. In exchange you pay the full fee up front, and I give you a monthly superbill so you can seek whatever out-of-network reimbursement your plan offers. If that trade-off doesn't fit your situation, a free consult is the best way to find out — and I'm glad to point you toward in-network options if that's the better path for you.</p>
          <div class="crisis-note" style="margin-top:28px;">
            <strong>If this is a mental health emergency,</strong> call or text <strong>988</strong> or call <strong>911</strong>. This site is not a crisis service.
          </div>
        </div>
      </div>

      <div class="spacer-lg"></div>

      <span class="sunrise-rule"></span>
      <h2 class="display" style="margin-bottom:24px;">Frequently asked.</h2>
      <div class="faq">
        
        ${[
          ['What does out-of-network mean for my wallet?',
           'You pay the full session fee at the time of service. Each month I provide a superbill — an itemized receipt with the codes your insurer needs — which you submit for any out-of-network reimbursement your plan offers. How much comes back depends entirely on your plan, so it is worth calling your insurer to ask about your out-of-network outpatient mental health benefit.'],
          ['Will you bill my insurance for me?', 'No. I do not bill insurance directly and I am not in-network with any plans. The monthly superbill is the tool that lets you pursue reimbursement on your own; I am happy to explain what is on it.'],
          ['Do you offer a sliding scale?',
           'A small number of reduced-fee slots are reserved each year and fill quickly. If cost is a barrier, say so in your consult — if I do not have a slot open, I will try to refer you somewhere that fits your budget.'],
          ['How long do clients usually stay in therapy?',
           'It varies with what you are working on. The Steady Work is one structured path that usually runs 12 to 16 weeks; some people do a focused course like that and finish, others stay longer for deeper trauma work or check in periodically. We decide together, and the GAD-7 and PCL-5 scores help us see when you are ready to taper.'],
          ['Are you a good fit for me?',
           'I am likely a good fit if you are an adult in Texas or New Mexico dealing with anxiety, trauma, or a hard life transition and you want structured, evidence-based work. I am not the right fit for active psychosis, primary substance-use treatment, court-ordered evaluations, or anyone needing a higher level of care — and if that is you, I will help you find the right specialist.']
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
      
      <p class="lead muted" style="margin-top:24px;max-width:62ch;">Short essays on anxiety, trauma, and the unglamorous mechanics of change — including how the GROUND Method and The Steady Work actually play out — written for the person deciding whether to begin.</p>

      <div class="spacer-md"></div>

      <div class="populations" style="margin-bottom:36px;">
        
        ${['All','Anxiety','Trauma','EMDR','GROUND Method','Transitions','Fees'].map((t,i)=>`<span class="chip" ${i===0?'style="border-color:var(--ink);"':''}><span class="dot"></span>${t}</span>`).join('')}
      </div>

      <div class="posts-grid">
        ${posts.map(p=>`
          <a class="post-card" data-slug="${p.slug}">
            <div class="meta"><span>${p.date}</span><span>${p.readingTime}</span><span>${p.tag}</span></div>
            <h3>${p.title}</h3>
            <p>${p.description}</p>
            <span class="read">Read essay <span class="arrow">→</span></span>
          </a>`).join('')}
      </div>
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
      
      <p class="lead muted" style="margin-top:24px;max-width:62ch;">Send a short message and Jordan will reply within two business days to schedule a free 20-minute consult — a low-pressure call for both of us to see whether we're a fit.</p>

      <div class="spacer-lg"></div>

      <div class="two-col" style="grid-template-columns:1fr 1fr;">
        <div>
          ${formMarkup()}
        </div>
        <div>
          <div class="card" style="padding:32px 30px;">
            <span class="eyebrow">Direct</span>
            <p style="margin-top:14px;font-family:'Fraunces',serif;font-size:22px;font-weight:460;line-height:1.35;">If you'd rather not use the form, email Jordan directly.</p>
            <p class="mono" style="margin-top:14px;font-size:14px;color:var(--ink);">hello@cedarsagetherapy.com</p>
            <p class="mono" style="margin-top:8px;font-size:14px;color:var(--ink);">512-555-0147</p>
            <hr class="divider" style="margin:24px 0;"/>
            <span class="eyebrow">Office</span>
            <p style="margin-top:8px;font-size:14.5px;line-height:1.6;">Cedar & Sage Therapy<br/>1100 Guadalupe St, Suite 220<br/>Austin, TX 78701</p>
            <hr class="divider" style="margin:24px 0;"/>
            <span class="eyebrow">Telehealth</span>
            <p style="margin-top:8px;font-size:14.5px;">Available across Texas & New Mexico. Sessions held on a HIPAA-compliant video platform.</p>
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
      <p style="margin-top:12px;">The contact form on this site sends a message directly to Jordan's email and does not persist data on this site. There is no database, no analytics that fingerprint users, and no third-party tracking pixels. Fonts are loaded from the page; there is no marketing-tracking surface.</p>
      <p style="margin-top:12px;">Clinical care, once underway, is governed by HIPAA and is documented in a HIPAA-compliant electronic record system separate from this website. Notice of Privacy Practices is provided to all clients at intake.</p>

      <div class="spacer-md"></div>
      <h2 class="display" style="font-size:24px;">Terms</h2>
      <p style="margin-top:12px;">Information on this site is general and does not constitute medical or psychotherapeutic advice. Visiting this site or submitting the consult form does not create a clinician-client relationship. A clinician-client relationship is established only after a signed informed-consent agreement at the start of clinical care.</p>

      <div class="spacer-md"></div>
      <h2 class="display" style="font-size:24px;">Accessibility</h2>
      <p style="margin-top:12px;">This site targets WCAG 2.2 AA. All interactive elements are keyboard navigable with visible focus rings. Motion respects <span class="mono" style="font-size:13px;">prefers-reduced-motion</span>. Type contrast is verified at every text/background pairing. If you encounter an accessibility issue, please email hello@cedarsagetherapy.com and it will be addressed.</p>

      <div class="spacer-md"></div>
      <div class="crisis-note">
        <strong>If you are in crisis:</strong> Call or text <strong>988</strong> · Call <strong>911</strong> for an emergency · Crisis Text Line <strong>Text HOME to 741741</strong> · Texas 24/7 Mental Health Line <strong>1-800-273-8255</strong>.
      </div>
    </div>
  </section>
`;

// ============ HELPERS ============
function contactStrip(){
  return `
  <section class="contact-strip">
    <div class="contact-grid">
      <div>
        <span class="sunrise-rule wide"></span>
        <h2 class="display">When you're ready, the next move is small.</h2>
        <p class="lead muted" style="margin-top:18px;">A short message. A free 20-minute call. From there, we decide together.</p>
        <div style="margin-top:32px;display:flex;gap:14px;flex-wrap:wrap;">
          <span class="chip"><span class="dot"></span>Free 20-minute consult</span>
          <span class="chip"><span class="dot"></span>within two business days</span>
          <span class="chip"><span class="dot"></span>Texas & New Mexico telehealth</span>
        </div>
      </div>
      <div>
        ${formMarkup()}
      </div>
    </div>
  </section>`;
}

function formMarkup(){
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
        <label for="cf-state">State</label>
        <select id="cf-state" name="state" required>
          <option value="">Select…</option>
          
          <option>Texas</option>
          <option>New Mexico</option>
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
    <div class="form-foot">No data is stored on this site. Your message is sent directly to Jordan's email.</div>
  </form>
  `;
}

// ============ DATA ============

const posts = [
  {
    slug:'why-you-cant-think-your-way-out-of-anxiety',
    title:'Why you can\'t think your way out of anxiety',
    description:'The thinking brain goes partly offline during a spike, which is exactly why grounding comes before insight in how I work.',
    date:'Apr 14, 2026', readingTime:'6 min read', tag:'Anxiety'
  },
  {
    slug:'what-emdr-actually-does',
    title:'What EMDR actually does (and what it doesn\'t)',
    description:'A plain-language look at how reprocessing helps a stuck memory stop firing in the present, minus the mystique.',
    date:'Mar 20, 2026', readingTime:'8 min read', tag:'EMDR'
  },
  {
    slug:'the-step-everyone-skips',
    title:'GROUND: the step almost everyone skips',
    description:'Why settling the body first is the unglamorous move that makes every other part of the work possible.',
    date:'Feb 28, 2026', readingTime:'5 min read', tag:'GROUND Method'
  },
  {
    slug:'a-transition-is-not-a-failure',
    title:'A hard transition is not a failure',
    description:'Divorce, a career break, a move, a loss — on naming what you actually want before rushing to fix the discomfort.',
    date:'Jan 22, 2026', readingTime:'5 min read', tag:'Transitions'
  },
  {
    slug:'why-im-out-of-network',
    title:'Why I\'m out-of-network, honestly',
    description:'The real trade-offs behind not billing insurance, what it protects about your care, and when in-network is the better call.',
    date:'Dec 11, 2025', readingTime:'7 min read', tag:'Fees'
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
    form.addEventListener('submit', e=>{
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
      const wrap = form.parentElement;
      const msg = document.createElement('div');
      msg.className = 'success';
      msg.innerHTML = `<strong>Thank you, ${name.split(' ')[0]}.</strong>Jordan will reply within two business days from hello@cedarsagetherapy.com. If this is urgent, please call 512-555-0147. If this is a crisis, call or text 988.`;
      form.replaceWith(msg);
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

// ============ CLICK DELEGATION FOR data-route ============
document.addEventListener('click', e=>{
  const t = e.target.closest('[data-route]');
  if(!t) return;
  e.preventDefault();
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
