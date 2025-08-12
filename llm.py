#!/usr/bin/env python3

"""
Multi-condition LLM tutoring experiment (single-file Flask app).
V3 - Complete UI/UX Overhaul
"""

import os
import random
import re
from datetime import timedelta
from functools import wraps
from flask import Flask, request, render_template_string, jsonify, session, redirect, url_for
from openai import OpenAI

# ---- Configuration ----
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-2025")
app.permanent_session_lifetime = timedelta(hours=6)

# Initialize Avalai/OpenAI client
client = OpenAI(
    api_key="aa-OLXKNUGEFrv21HktfLjczPEGUyS59U0rjIITsySapwJNn3Kx",
    base_url="https://api.avalai.ir/v1",
)

SYSTEM_PROMPT_BASE = (
    "You are an intelligent tutoring assistant named Mr. G. "
    "You are interacting with a student in an experiment. Be friendly, concise, and pedagogical. "
    "Provide step-by-step explanations, hints, and short examples. "
    "When the user asks for a solution, offer a brief outline first, then optionally show the full solution if requested. "
    "Format your responses using Markdown. For mathematical formulas, use LaTeX syntax enclosed in $...$ for inline math and $$...$$ for display math."
    "You're primarly language is Farsi or Persian"
)

DIMENSION_NAMES = ["Active-Reflective", "Sensing-Intuitive", "Visual-Verbal", "Sequential-Global"]

# ---- Timeline and Stage Management ----
ALL_STAGES = {
    'fslsm': 'پرسشنامه یادگیری',
    'chat1': 'گفتگو ۱',
    'exam1': 'آزمون ۱',
    'chat2': 'گفتگو ۲',
    'exam2': 'آزمون ۲',
    'chat3': 'گفتگو ۳',
    'exam3': 'آزمون ۳',
    'post_test': 'پرسشنامه نهایی',
}
ORDERED_STAGES = list(ALL_STAGES.keys())

def generate_timeline_html(current_stage_key):
    html = '<div class="timeline-bar">'
    try:
        if current_stage_key == 'end': current_index = len(ORDERED_STAGES)
        else: current_index = ORDERED_STAGES.index(current_stage_key)
    except (ValueError, TypeError): current_index = -1
    for i, stage_key in enumerate(ORDERED_STAGES):
        stage_name, status = ALL_STAGES[stage_key], 'future'
        if i < current_index: status = 'completed'
        elif i == current_index: status = 'current'
        html += f'<div class="timeline-segment {status}" title="{stage_name}"><div class="timeline-label">{stage_name}</div></div>'
    html += '</div>'
    return html

# ---- Base HTML Layout ----
LAYOUT_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ title }} - آزمایش سیستم تدریس هوشمند</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700&display=swap');
    :root {
        --primary-color: #0d47a1; /* Deep Blue */
        --accent-color: #ffab00; /* Amber/Gold */
        --success-color: #388e3c; /* Green */
        --light-gray: #f5f5f5;
        --dark-gray: #424242;
        --text-color: #212121;
        --border-color: #e0e0e0;
    }
    body { font-family: 'Vazirmatn', Arial, sans-serif; background: var(--light-gray); padding: 2rem; direction: rtl; color: var(--text-color); }
    .container { max-width: 800px; margin: auto; background: white; padding: 2.5rem; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border-top: 4px solid var(--primary-color); }
    h1, h2, h3 { text-align: center; color: var(--primary-color); }
    h1 { font-size: 2.2rem; }
    h2 { font-size: 1.8rem; }
    p, li { line-height: 1.8; font-size: 1.1rem; }
    .button { display: inline-block; text-decoration: none; background: linear-gradient(145deg, var(--accent-color), #ffc107); color: var(--text-color); font-weight: bold; padding: 0.9rem 1.8rem; margin: 1.5rem 0; border: none; border-radius: 8px; font-family: 'Vazirmatn', sans-serif; font-size: 1.1rem; cursor: pointer; transition: all 0.3s ease; box-shadow: 0 2px 5px rgba(0,0,0,0.15); }
    .button:hover { transform: translateY(-3px); box-shadow: 0 4px 10px rgba(0,0,0,0.2); }
    .center { text-align: center; }
    form { margin-top: 1.5rem; }
    .form-group { margin-bottom: 1.5rem; }
    .form-group label { display: block; margin-bottom: 0.75rem; font-weight: bold; font-size: 1.1rem; color: var(--dark-gray); }
    .form-group input, .form-group textarea { width: 100%; padding: 0.75rem; border: 1px solid var(--border-color); border-radius: 8px; box-sizing: border-box; font-family: 'Vazirmatn', sans-serif; font-size: 1rem; transition: border-color 0.3s, box-shadow 0.3s; }
    .form-group input:focus, .form-group textarea:focus { border-color: var(--accent-color); box-shadow: 0 0 0 3px rgba(255,171,0,0.25); outline: none; }
    /* Timeline Styles */
    .timeline-container { margin-bottom: 2.5rem; }
    .timeline-bar { display: flex; width: 100%; height: 25px; background-color: #e9ecef; border-radius: 8px; overflow: hidden; border: 1px solid var(--border-color); }
    .timeline-segment { flex: 1; transition: all 0.5s ease; display: flex; align-items: center; justify-content: center; border-left: 1px solid rgba(255,255,255,0.7); position: relative; }
    .timeline-segment:first-child { border-left: none; }
    .timeline-segment.completed { background-color: var(--success-color); }
    .timeline-segment.current { background-color: var(--primary-color); transform: scale(1.05); z-index: 10; box-shadow: 0 0 10px rgba(13,71,161,0.5); }
    .timeline-segment.future { background-color: #e9ecef; }
    .timeline-label { color: white; font-weight: 500; font-size: 0.8rem; text-shadow: 1px 1px 1px rgba(0,0,0,0.2); opacity: 0; transition: opacity 0.3s; white-space: nowrap; }
    .timeline-segment:hover .timeline-label, .timeline-segment.current .timeline-label { opacity: 1; }
    .timeline-segment.future .timeline-label { color: #6c757d; text-shadow: none; }
  </style>
</head>
<body><div class="container"> <div class="timeline-container"> __TIMELINE_PLACEHOLDER__ </div> <h1>{{ title }}</h1> __CONTENT_PLACEHOLDER__ </div></body>
</html>
"""

# ---- Flow Control & Session Management ----
def participant_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'participant' not in session: return redirect(url_for('homepage'))
        return f(*args, **kwargs)
    return decorated_function

def set_stage(stage):
    if 'participant' in session:
        session['participant']['stage'] = stage
        session.modified = True

def get_stage():
    return session.get('participant', {}).get('stage')

# ---- Heuristics and Scoring ----
def nudge_fslsm_from_text(text, multiplier=1): return {}
def compute_fslsm_scores(form_data): return {name: 0 for name in DIMENSION_NAMES}
# ---- LLM and Conversation Helpers ----
def initialize_participant_session(name, fslsm_scores, group):
    session['participant'] = {'name': name, 'fslsm': fslsm_scores, 'group': group, 'stage': 'chat1', 'conversation': []}
    session.modified = True
def add_to_conversation(role, content):
    if 'participant' in session: session['participant'].setdefault('conversation', []).append({'role': role, 'content': content}); session.modified = True
def call_llm(messages, temperature=0.2, max_tokens=5000):
    try: return client.chat.completions.create(model=os.environ.get('LLM_MODEL', 'grok-3-mini-latest'), messages=messages, temperature=temperature, max_tokens=max_tokens).choices[0].message.content.strip()
    except Exception as exc: return f"**[LLM Error]** {exc}"

# ---- Routes ----
@app.route('/')
def homepage():
    session.clear()
    timeline_html = generate_timeline_html(None)
    page_content = """
      <p style="text-align: center;">به پلتفرم آزمایش سیستم تدریس هوشمند خوش آمدید.</p>
      <h2>روند کلی آزمایش</h2>
      <ol style="list-style-type: none; padding-right: 20px;">
        <li style="margin-bottom:0.5rem;">۱. پرسشنامه اولیه برای تعیین سبک یادگیری شما</li>
        <li style="margin-bottom:0.5rem;">۲. سه جلسه گفتگوی آموزشی با دستیار هوشمند (آقای G)</li>
        <li style="margin-bottom:0.5rem;">۳. سه آزمون کوتاه بعد از هر جلسه گفتگو</li>
        <li style="margin-bottom:0.5rem;">۴. پرسشنامه نهایی برای ارزیابی تجربه شما</li>
      </ol>
      <div class="center">
        <a href="{{ url_for('fslsm_questionnaire') }}" class="button">بزن بریم!</a>
      </div>
    """
    full_html = LAYOUT_HTML.replace("__TIMELINE_PLACEHOLDER__", timeline_html).replace("__CONTENT_PLACEHOLDER__", page_content)
    return render_template_string(full_html, title="پرتال آزمایش")

@app.route('/fslsm')
def fslsm_questionnaire():
    timeline_html = generate_timeline_html('fslsm')
    page_content = """
      <style>
        .fslsm-question { border: 1px solid var(--border-color); padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem; }
        .fslsm-question h3 { margin-top: 0; color: var(--dark-gray); font-size: 1.2rem; }
        .fslsm-options label { display: block; background: #f9f9f9; padding: 0.75rem; border-radius: 5px; margin-bottom: 0.5rem; cursor: pointer; transition: all 0.2s; border: 1px solid transparent; }
        .fslsm-options label:hover { background: #f0f0f0; }
        .fslsm-options input[type='radio'] { display: none; }
        .fslsm-options input[type='radio']:checked + span { font-weight: bold; color: var(--primary-color); }
        .fslsm-options input[type='radio']:checked + span::before { content: '✔ '; }
        .fslsm-options label:has(input:checked) { border-color: var(--accent-color); background: #fff8e1; }
      </style>
      <form id="quizForm" method="post" action="{{ url_for('submit_fslsm') }}">
        <div class="form-group">
          <label for="name">نام و نام خانوادگی (یا نام مستعار)</label>
          <input type="text" id="name" name="name" placeholder="مثال: سارا رضایی" required>
        </div>
        <div id="questions"></div>
        <div class="center"> <button type="submit" id="submitBtn" class="button">ثبت و شروع گفتگو</button> </div>
      </form>
    <script>
        const questions = [
            { q: "۱) هنگامی مطلب را بهتر می فهمیم که:", a: "آن را آزمایش می کنم.", b: "درباره آن کاملاً فکر می کنم."}, { q: "۲) ترجیح می دهم:", a: "واقع بین به نظر برسم.", b: "مبتکر به نظر برسم."}, { q: "۳) وقتی به آنچه دیروز انجام داده ام فکر می کنم، بیشتر:", a: "آن را به صورت تصویر به یاد می آورم.", b: "آن را به صورت کلمات به یاد می آورم."}, { q: "۴) معمولاً:", a: "جزئیات موضوع را می فهمم، اما درباره ساختار کلی آن گیج می شوم.", b: "ساختار کلی موضوع را می فهمم، اما درباره جزئیات آن گیج می شوم."}, { q: "۵) برای یادگیری هر چیز تازه:", a: "صحبت کردن درباره آن به من کمک می کند.", b: "فکر کردن درباره آن به من کمک می کند."}, { q: "۶) اگر معلم شوم، ترجیح می دهم درسی بدهم که:", a: "با حقایق زندگی سروکار داشته باشد.", b: "با عقاید و نظریه ها سروکار داشته باشد."}, { q: "۷) ترجیح می دهم مطالب جدید را از طریق:", a: "تصاویر، جدولها و نقشه ها یاد بگیرم.", b: "دستورالعملهای مکتوب یا اطلاعات شفاهی یاد بگیرم."}, { q: "۸) وقتی:", a: "همه اجزای مطلب را بفهمم، کل مطلب را می فهمم.", b: "کل مطلب را بفهمم، همه اجزای آن را می فهمم."}, { q: "۹) در میان گروهی که مسئله دشواری را بررسی می کنند، من به احتمال زیاد:", a: "وارد بحث می شوم و عقیده ام را بیان می کنم.", b: "در گوشه ای می نشینم و گوش می دهم."}, { q: "۱۰) یادگیری:", a: "واقعیات را آسان تر می دانم.", b: "مفاهیم را آسان تر می دانم."}, { q: "۱۱) هنگام مطالعه کتابی که تصاویر و شکلهای بسیار زیادی دارد، به احتمال زیاد:", a: "تصاویر و نمودارها را به دقت بررسی می کنم.", b: "توجه خود را به نوشته های کتاب معطوف می کنم."}, { q: "۱۲) هنگام حل مسائل ریاضی:", a: "معمولاً مرحله به مرحله روی راه حلهایی که به جواب می رسند کار می کنم.", b: "غالباً ابتدا راه حلها را بررسی می کنم و سپس سعی می کنم مراحلی که برای رسیدن به آنها لازم است بیابم."}, { q: "۱۳) وقتی در کلاسی شرکت می کنم:", a: "معمولاً با بسیاری از دانش آموزان آشنا می شوم.", b: "معمولاً با تعداد کمی از دانش آموزان آشنا می شوم."}, { q: "۱۴) در مطالعه مطالب واقعی، ترجیح می دهم مطالب:", a: "چیزهای جدیدی به من بیاموزند یا به من چگونگی انجام دادن کارها را یاد بدهند.", b: "ایده های جدیدی برای فکر کردن درباره آنها در اختیار من بگذراند."}, { q: "۱۵) معلمانی را دوست دارم که هنگام درس دادن:", a: "جدولها و نمودارهای زیادی روی تخته می کشند.", b: "زمان زیادی را صرف توضیح دادن می کنند."}, { q: "۱۶) هنگام تحلیل داستان یا رمان:", a: "به اتفاقات داستان فکر می کنم و می کوشم آنها را به منظور فهم موضوع اصلی داستان به یکدیگر مرتبط سازم.", b: "چون وقتی که داستان را تمام می کنم فقط موضوع اصلی آن را به خاطر می آورم، باید به عقب برگردم و رابطه بین اتفاقهای داستان را پیدا کنم."}, { q: "۱۷) وقتی حل مسئله را شروع می کنم، به احتمال زیاد:", a: "بلافاصله روی راه حل آن کار می کنم.", b: "ابتدا سعی می کنم مسئله را کاملاً بفهمم."}, { q: "۱۸) بیشتر:", a: "عقاید قطعی را ترجیح می دهم.", b: "فرضیات را ترجیح می دهم."}, { q: "۱۹) آنچه را:", a: "می بینم بهتر به یاد می آورم.", b: "می شنوم بهتر به یاد می آورم."}, { q: "۲۰) برای من خیلی مهم است که معلم:", a: "مطالب را با نظم و ترتیب روشن ارائه دهد.", b: "تصویری کلی از مطالب را ارائه دهد و آن را با موضوعات دیگر مرتبط سازد."}, { q: "۲۱) ترجیح می دهم:", a: "در گروه مطالعه کنم.", b: "به تنهایی مطالعه کنم."}, { q: "۲۲) بیشتر ترجیح می دهم:", a: "درباره جزئیات کار دقیق باشم.", b: "در چگونگی انجام دادن کار خلاق باشم."}, { q: "۲۳) برای پیدا کردن محلی ناآشنا:", a: "استفاده از نقشه را ترجیح می دهم.", b: "استفاده از آدرس مکتوب را ترجیح می دهم."}, { q: "۲۴) مطالب را:", a: "در مراحل نسبتاً منظم و با تلاش زیاد یاد می گیرم.", b: "در ابتدا خوب نمی فهمم و کاملاً گیج می شوم، اما ناگهان آن را یاد می گیرم."}, { q: "۲۵) ترجیح می دهم ابتدا:", a: "کارها را انجام دهم.", b: "در باره چگونگی انجام دادن کارها فکر کنم."}, { q: "۲۶) وقتی برای سرگرمی مطالعه می کنم، نویسندگانی را ترجیح می دهم که:", a: "به روشنی منظورشان را بیان می کنند.", b: "مطالب را به روشهای جالب و خلاق بیان می کنند."}, { q: "۲۷) وقتی در کلاس تصویر یا شکلی می بینم، احتمال زیادی وجود دارد که:", a: "تصویر یا شکل را به یاد بیاورم.", b: "توضیحات معلم درباره تصویر یا شکل را به یاد بیاورم."}, { q: "۲۸) هنگامی که با اطلاعات زیادی مواجه می شوم به احتمال زیاد:", a: "به جزئیات توجه می کنم و اصل مطلب را از دست می دهم.", b: "سعی می کنم، قبل از پرداختن به جزئیات، اصل مطلب را بفهمم."}, { q: "۲۹) یادآوری:", a: "آنچه را انجام داده ام آسان تر می دانم.", b: "آنچه را درباره اش زیاد فکر کرده ام، آسان تر می دانم."}, { q: "۳۰) وقتی باید کاری انجام دهم، ترجیح می دهم:", a: "برای انجام دادن آن در یکی از روشهای موجود مهارت کسب کنم.", b: "روشهای جدیدی ابداع کنم و به کار گیرم."}, { q: "۳۱) وقتی فردی متنی به من نشان می دهد:", a: "شکلها و تصاویر آن را ترجیح می دهم.", b: "خلاصه متن و نتایج آن را ترجیح می دهم."}, { q: "۳۲) برای تدوین مقاله، به احتمال زیاد:", a: "نگارش مقاله را از ابتدا شروع می کنم و با رعایت ترتیب بخشها ادامه می دهم.", b: "بخشهای مختلف مقاله را بدون توجه به ترتیب آنها آماده و سپس مرتب می کنم."}, { q: "۳۳) وقتی باید با دیگران به صورت گروهی کار کنم، مایلم در آغاز:", a: "هر یک از افراد گروه عقاید و نظرهایشان را مطرح کنند.", b: "افراد عقاید خود را ابتدا به صورت انفرادی بررسی و سپس در گروه مطرح کنند."}, { q: "۳۴) به نظر من بالاترین تمجید آن است که فرد را:", a: "معقول بدانیم.", b: "دارای تخیل قوی بدانیم."}, { q: "۳۵) اگر افرادی را در میهمانی ملاقات کنم، احتمال زیادی وجود دارد که:", a: "چهره آنها را به یاد بیاورم.", b: "آنچه را درباره خودشان گفته اند به یاد بیاورم."}, { q: "۳۶) وقتی موضوع جدیدی یاد می گیرم، ترجیح می دهم:", a: "بر آن متمرکز شوم و تا آنجا که می توانم درباره آن مطالبی یاد بگیرم.", b: "آن موضوع را با موضعهای دیگر مرتبط کنم."}, { q: "۳۷) به نظر دیگران، من:", a: "خوش برخورد به شمار می آیم.", b: "خوددار به شمار می آیم."}, { q: "۳۸) دروسی را ترجیح می دهم که بر:", a: "موضوعات عینی مانند واقعیات و اطلاعات متمرکز باشند.", b: "موضوعات انتزاعی مانند مفاهیم و نظریه ها متمرکز باشند."}, { q: "۳۹) برای سرگرمی، ترجیح می دهم:", a: "تلویزیون تماشا کنم.", b: "کتاب بخوانم."}, { q: "۴۰) بعضی از معلمان درس خود را با خلاصه ای از موضوع مورد بحث شروع می کنند، این خلاصه ها برای من:", a: "کمی مفید هستند.", b: "بسیار مفید هستند."}, { q: "۴۱) وقتی تکلیف به صورت گروهی انجام می شود، اختصاص یک نمره برای کل گروه:", a: "درست است.", b: "درست نیست."}, { q: "۴۲) در محاسبات طولانی، تمایل به:", a: "مرور تمامی مراحل و کنترل دقیق محاسبات دارم.", b: "مرور تمامی مراحل و کنترل دقیق محاسبات ندارم و باید خود را مجبور به انجام دادن آن کنم."}, { q: "۴۳) تجسم مکانهایی که در آنها بوده ام برای من:", a: "نسبتاً آسان، کامل و دقیق است.", b: "دشوار، بدون جزئیات و بی دقت است."}, { q: "۴۴) هنگام حل مسائل به صورت گروهی، بیشتر مایلم:", a: "در مورد مراحل حل مسئله فکر کنم.", b: "درباره نتایج و کاربردهای احتمالی راه حلها فکر کنم."}
        ];
        const container = document.getElementById("questions");
        questions.forEach((q, i) => {
            const div = document.createElement("div");
            div.className = "fslsm-question";
            div.innerHTML = `<h3>${q.q}</h3><div class="fslsm-options"><label><input type="radio" name="q${i}" value="A" required><span>${q.a}</span></label><label><input type="radio" name="q${i}" value="B" required><span>${q.b}</span></label></div>`;
            container.appendChild(div);
        });
    </script>
    """
    full_html = LAYOUT_HTML.replace("__TIMELINE_PLACEHOLDER__", timeline_html).replace("__CONTENT_PLACEHOLDER__", page_content)
    return render_template_string(full_html, title="پرسشنامه سبک یادگیری")

@app.route('/submit_fslsm', methods=['POST'])
def submit_fslsm():
    name = request.form.get('name')
    if not name: return redirect(url_for('fslsm_questionnaire'))
    fslsm_scores = compute_fslsm_scores(request.form)
    assigned_group = random.choice(['A', 'B', 'C', 'D'])
    starting_fslsm = {k: 0 for k in DIMENSION_NAMES} if assigned_group == 'B' else fslsm_scores.copy()
    initialize_participant_session(name, starting_fslsm, assigned_group)
    session['original_fslsm'] = fslsm_scores
    return redirect(url_for('chat_page'))

@app.route('/chat')
@participant_required
def chat_page():
    stage = get_stage()
    timeline_html = generate_timeline_html(stage)
    next_info = {
        'chat1': ('رفتن به آزمون اول', url_for('exam', exam_id=1)),
        'chat2': ('رفتن به آزمون دوم', url_for('exam', exam_id=2)),
        'chat3': ('رفتن به آزمون سوم', url_for('exam', exam_id=3)),
    }.get(stage)
    next_step_text, next_step_url = (next_info[0], next_info[1]) if next_info else (None, None)
    return render_template_string("""
<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Chat with Mr. G</title>
  <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root { --primary-color: #0d47a1; --accent-color: #ffab00; --app-bg: #fff; --chat-bg: #f4f7f9; --user-msg-bg: linear-gradient(135deg, #007bff, #0056b3); --assistant-msg-bg: #e9ecef;}
    body{font-family:'Vazirmatn',sans-serif;background:var(--chat-bg);margin:0;padding:1rem;display:flex;justify-content:center;align-items:center;height:100vh;box-sizing:border-box;}
    #app{width:100%;max-width:900px;background:var(--app-bg);border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,0.1);overflow:hidden;display:flex;flex-direction:column;height:90vh;}
    .chat-header{padding:1rem;border-bottom:1px solid #dee2e6;background:var(--app-bg);}
    .header-content{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;}
    .header-info h3 {margin:0;color:#0d47a1;}
    .header-actions{display:flex;gap:10px;align-items:center;}
    .header-actions a{text-decoration:none;}
    #messages{flex:1;padding:1rem;overflow-y:auto;background:var(--chat-bg);background-image:url('data:image/svg+xml,<svg width="60" height="60" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><g fill="%23e0e0e0" fill-opacity="0.4"><path d="M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z"/></g></g></svg>');}
    .message{display:flex;gap:10px;max-width:85%;margin-bottom:1rem;align-items:flex-end;}
    .message-content{padding:.75rem 1.25rem;border-radius:20px;line-height:1.7;box-shadow:0 1px 4px rgba(0,0,0,0.1);}
    /* --- RTL Message Alignment --- */
    .user{justify-content:flex-end;margin-left:auto;}
    .assistant{justify-content:flex-start;margin-right:auto;}
    .user .message-content{background:var(--user-msg-bg);color:white;border-bottom-right-radius:5px;}
    .assistant .message-content{background:var(--assistant-msg-bg);color:#212529;border-bottom-left-radius:5px;}
    .avatar{width:40px;height:40px;border-radius:50%;background:var(--primary-color);color:white;display:flex;align-items:center;justify-content:center;font-weight:bold;flex-shrink:0;box-shadow:0 1px 3px rgba(0,0,0,0.2);}
    #inputbar{display:flex;border-top:1px solid #dee2e6;padding:.75rem;gap:.75rem;background:var(--app-bg);align-items:flex-end;}
    textarea{flex:1;padding:.9rem;border-radius:20px;border:1px solid #ced4da;resize:none;font-family:inherit;max-height:150px;text-align:right;font-size:1rem;}
    textarea:focus{border-color:var(--accent-color);box-shadow:0 0 0 3px rgba(255,171,0,0.25);outline:none;}
    button{border:none;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background-color .2s;}
    button#sendBtn{background-color:var(--primary-color);color:white;width:44px;height:44px;flex-shrink:0;}
    button#sendBtn:disabled{background-color:#adb5bd;}
    button.button-style {border-radius:8px;padding:.6rem .9rem;font-family:'Vazirmatn';}
    button.next-step-btn{background-color:#28a745;color:white;}
    button#restartBtn{background-color:#6c757d;color:white;}
    .typing-indicator span{height:8px;width:8px;background-color:#999;border-radius:50%;display:inline-block;animation:bob 1.4s infinite ease-in-out both;}
    .typing-indicator span:nth-child(1){animation-delay:-.32s} .typing-indicator span:nth-child(2){animation-delay:-.16s}
    @keyframes bob{0%,80%,100%{transform:scale(0)}40%{transform:scale(1.0)}}
    /* Timeline Styles */
    .timeline-bar{display:flex;width:100%;height:25px;background-color:#e9ecef;border-radius:8px;overflow:hidden;border:1px solid #dee2e6;}
    .timeline-segment{flex:1;transition:all .5s ease;display:flex;align-items:center;justify-content:center;border-left:1px solid hsla(0,0%,100%,.7);position:relative;}
    .timeline-segment:first-child{border-left:none;}
    .timeline-segment.completed{background-color:#28a745;}
    .timeline-segment.current{background-color:var(--primary-color);transform:scale(1.05);z-index:10;box-shadow:0 0 10px rgba(13,71,161,0.5);}
    .timeline-segment.future{background-color:#e9ecef;}
    .timeline-label{color:#fff;font-weight:500;font-size:.8rem;text-shadow:1px 1px 1px rgba(0,0,0,.2);opacity:0;transition:opacity .3s;white-space:nowrap;}
    .timeline-segment:hover .timeline-label, .timeline-segment.current .timeline-label{opacity:1;}
    .timeline-segment.future .timeline-label{color:#6c757d;text-shadow:none;}
  </style>
</head>
<body>
  <div id="app">
    <header class="chat-header">
      <div class="header-content">
        <div class="header-info"><h3 style="margin:0">آقای G</h3><div id="meta" style="font-size:0.9rem;color:#666;margin-top:4px;"></div></div>
        <div class="header-actions">{% if next_step_url %}<a href="{{ next_step_url }}"><button class="button-style next-step-btn">{{ next_step_text }}</button></a>{% endif %}<button id="restartBtn" class="button-style">شروع مجدد</button></div>
      </div>
      <div class="timeline-container">{{ timeline_html|safe }}</div>
    </header>
    <main id="messages"></main>
    <div id="inputbar">
      <textarea id="input" rows="1" placeholder="سوال خود را بپرسید..."></textarea>
      <button id="sendBtn" title="ارسال"><svg fill="currentColor" viewBox="0 0 20 20" height="1em" width="1em"><path d="M3.105 3.105a1 1 0 00-1.414 1.414L10 12.929l-1.414 1.414a1 1 0 001.414 1.414l5-5a1 1 0 000-1.414l-5-5z" clip-rule="evenodd" fill-rule="evenodd"></path></svg></button>
    </div>
  </div>
<script>
const messagesEl = document.getElementById('messages'); const inputEl = document.getElementById('input'); const sendBtn = document.getElementById('sendBtn');
function addMessage(htmlContent, role) { const messageWrapper = document.createElement('div'); messageWrapper.className = `message ${role}`; let avatarHtml = role === 'assistant' ? '<div class="avatar">G</div>' : ''; messageWrapper.innerHTML = `${avatarHtml}<div class="message-content">${htmlContent}</div>`; messagesEl.appendChild(messageWrapper); messagesEl.scrollTop = messagesEl.scrollHeight; }
async function loadData(){ const p_res=await fetch('/participant'); const p_data=await p_res.json(); if(p_data.name)document.getElementById('meta').textContent=`شرکت‌کننده: ${p_data.name} | گروه: ${p_data.group}`; const h_res=await fetch('/history'); const h_data=await h_res.json(); if(h_data.history)h_data.history.forEach(m=>addMessage(marked.parse(m.content),m.role==='user'?'user':'assistant'));}
async function sendMessage() { const text = inputEl.value.trim(); if(!text) return; addMessage(marked.parse(text), 'user'); inputEl.value=''; inputEl.style.height='auto'; sendBtn.disabled=true; const indicator = document.createElement('div'); indicator.className = 'message assistant'; indicator.innerHTML = `<div class="avatar">G</div><div class="message-content typing-indicator"><span></span><span></span><span></span></div>`; messagesEl.appendChild(indicator); messagesEl.scrollTop = messagesEl.scrollHeight; try { const res = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})}); const data = await res.json(); indicator.querySelector('.message-content').innerHTML = marked.parse(data.reply || '(پاسخی دریافت نشد)'); } catch(e){ indicator.querySelector('.message-content').innerHTML = '**[خطای اتصال]**'; } finally { sendBtn.disabled=false; inputEl.focus(); }}
sendBtn.addEventListener('click', sendMessage);
inputEl.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
inputEl.addEventListener('input', () => { inputEl.style.height = 'auto'; inputEl.style.height = (inputEl.scrollHeight) + 'px'; });
document.getElementById('restartBtn').addEventListener('click', () => { if (confirm("آیا مطمئن هستید؟ تمام پیشرفت شما پاک خواهد شد.")) window.location.href = '/'; });
window.addEventListener('load', async () => { await loadData(); inputEl.focus(); });
</script>
</body></html>""", timeline_html=timeline_html, next_step_url=next_step_url, next_step_text=next_step_text)

@app.route('/exam/<int:exam_id>')
@participant_required
def exam(exam_id):
    current_stage = get_stage()
    expected_chat_stage, expected_exam_stage = f'chat{exam_id}', f'exam{exam_id}'
    if current_stage == expected_chat_stage: set_stage(expected_exam_stage); current_stage = expected_exam_stage
    if current_stage != expected_exam_stage: return redirect(url_for('chat_page') if 'chat' in str(get_stage()) else 'homepage')
    timeline_html = generate_timeline_html(current_stage)
    page_content = """
      <style>
        fieldset { border: 1px solid var(--border-color); border-radius: 8px; padding: 1.5rem; margin-bottom: 2rem; }
        legend { padding: 0 1rem; font-weight: bold; color: var(--primary-color); }
        .mcq-option { display: block; background: #f9f9f9; padding: 0.75rem 1.25rem; border-radius: 8px; margin-bottom: 0.5rem; cursor: pointer; transition: all 0.2s; border: 1px solid transparent; }
        .mcq-option:hover { background: #f0f0f0; }
        .mcq-option input[type='radio'] { display: none; }
        .mcq-option input[type='radio']:checked + span { font-weight: bold; color: var(--primary-color); }
        .mcq-option:has(input:checked) { border-color: var(--accent-color); background: #fff8e1; }
      </style>
      <p style="text-align:center;">لطفاً به سوالات زیر با دقت پاسخ دهید.</p>
      <form method="post" action="{{ url_for('submit_exam', exam_id=exam_id) }}">
        <fieldset>
          <legend>سوال ۱</legend>
          <p>مفهوم اصلی که در گفتگوی اخیر مطرح شد چه بود؟</p>
          <div class="mcq-option"><label><input type="radio" name="q1" value="a" required><span>گزینه الف</span></label></div>
          <div class="mcq-option"><label><input type="radio" name="q1" value="b" required><span>گزینه ب</span></label></div>
          <div class="mcq-option"><label><input type="radio" name="q1" value="c" required><span>گزینه ج</span></label></div>
        </fieldset>
        <fieldset>
          <legend>سوال ۲</legend>
          <p>کدام یک از موارد زیر به درستی به کار رفته است؟</p>
          <div class="mcq-option"><label><input type="radio" name="q2" value="a" required><span>گزینه ۱</span></label></div>
          <div class="mcq-option"><label><input type="radio" name="q2" value="b" required><span>گزینه ۲</span></label></div>
        </fieldset>
        <div class="center"><button type="submit" class="button">ارسال پاسخ‌ها و ادامه</button></div>
      </form>
    """
    full_html = LAYOUT_HTML.replace("__TIMELINE_PLACEHOLDER__", timeline_html).replace("__CONTENT_PLACEHOLDER__", page_content)
    return render_template_string(full_html, title=f"آزمون شماره {exam_id}", exam_id=exam_id)

@app.route('/submit_exam/<int:exam_id>', methods=['POST'])
@participant_required
def submit_exam(exam_id):
    if exam_id == 3: set_stage('post_test'); return redirect(url_for('post_test'))
    else: set_stage(f'chat{exam_id + 1}'); return redirect(url_for('chat_page'))

@app.route('/post_test')
@participant_required
def post_test():
    if get_stage() != 'post_test': return redirect(url_for('homepage'))
    timeline_html = generate_timeline_html('post_test')
    page_content = """
      <p style="text-align:center;">این آخرین مرحله است! لطفاً نظر خود را درباره تجربه این آزمایش با ما در میان بگذارید.</p>
      <form method="post" action="{{ url_for('submit_post_test') }}">
        <div class="form-group">
            <label>۱. به طور کلی، دستیار هوشمند چقدر در یادگیری به شما کمک کرد؟ (۱=خیلی کم، ۵=خیلی زیاد)</label>
            <input type="range" name="q1_rating" min="1" max="5" value="3" style="width:100%">
        </div>
        <div class="form-group">
            <label for="q2_feedback">۲. چه چیزی را در مورد تعامل با دستیار هوشمند بیشتر دوست داشتید؟</label>
            <textarea name="q2_feedback" rows="4"></textarea>
        </div>
        <div class="center"> <button type="submit" class="button">پایان و ارسال</button> </div>
      </form>
    """
    full_html = LAYOUT_HTML.replace("__TIMELINE_PLACEHOLDER__", timeline_html).replace("__CONTENT_PLACEHOLDER__", page_content)
    return render_template_string(full_html, title="پرسشنامه نهایی")

@app.route('/submit_post_test', methods=['POST'])
@participant_required
def submit_post_test():
    set_stage('end'); return redirect(url_for('end_page'))

@app.route('/end')
def end_page():
    timeline_html = generate_timeline_html('end')
    page_content = """
      <h2 style="color: var(--success-color);">آزمایش با موفقیت به پایان رسید.</h2>
      <p style="text-align: center;">از مشارکت و زمان شما در این تحقیق بسیار سپاسگزاریم. اکنون می‌توانید این صفحه را ببندید.</p>
    """
    full_html = LAYOUT_HTML.replace("__TIMELINE_PLACEHOLDER__", timeline_html).replace("__CONTENT_PLACEHOLDER__", page_content)
    session.clear()
    return render_template_string(full_html, title="پایان")

# ---- API Routes for Chat Functionality ----
@app.route('/api/chat', methods=['POST'])
@participant_required
def api_chat():
    message = (request.get_json() or {}).get('message', '').strip()
    if not message: return jsonify({'error': 'Empty message'}), 400
    participant = session['participant']
    group = participant.get('group', 'D')
    system_prompt = SYSTEM_PROMPT_BASE
    if group == 'A': system_prompt += f"\n\nLearner FSLSM profile: {participant.get('fslsm')}. Adapt dynamically."
    elif group == 'B': system_prompt += "\n\nStart with no FSLSM info. Learn and adapt dynamically."
    elif group == 'C': system_prompt += f"\n\nLearner FSLSM profile: {participant.get('fslsm')}. Do NOT adapt."
    messages = [{'role': 'system', 'content': system_prompt}]
    messages.extend(participant.get('conversation', [])[-12:])
    messages.append({'role': 'user', 'content': message})
    reply = call_llm(messages)
    add_to_conversation('user', message)
    add_to_conversation('assistant', reply)
    return jsonify({'reply': reply})

@app.route('/participant')
@participant_required
def participant_info():
    p = session.get('participant', {})
    return jsonify({'name': p.get('name'), 'group': p.get('group')})

@app.route('/history')
@participant_required
def history():
    return jsonify({'history': session.get('participant', {}).get('conversation', [])})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))