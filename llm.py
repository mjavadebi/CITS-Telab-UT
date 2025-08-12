#!/usr/bin/env python3
"""
Multi-condition LLM tutoring experiment (single-file Flask app).

Timeline:
- Homepage -> FSLSM -> Chat 1 -> Exam 1 -> Chat 2 -> Exam 2 -> Chat 3 -> Exam 3 -> Post-Test -> End
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
    """Generates the HTML for the progress timeline bar."""
    html = '<div class="timeline-bar">'
    try:
        # If the stage is 'end', show all as completed
        if current_stage_key == 'end':
            current_index = len(ORDERED_STAGES)
        else:
            current_index = ORDERED_STAGES.index(current_stage_key)
    except (ValueError, TypeError):
        current_index = -1

    for i, stage_key in enumerate(ORDERED_STAGES):
        stage_name = ALL_STAGES[stage_key]
        status = 'future'
        if i < current_index:
            status = 'completed'
        elif i == current_index:
            status = 'current'
        
        html += f'<div class="timeline-segment {status}" title="{stage_name}">'
        html += f'<div class="timeline-label">{stage_name}</div>'
        html += '</div>'
    
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
    body { font-family: 'Vazirmatn', Arial, sans-serif; background: #f4f4f4; padding: 2rem; direction: rtl; color: #333; }
    .container { max-width: 800px; margin: auto; background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    h1, h2, h3 { text-align: center; }
    p, li { line-height: 1.8; }
    .button { display: inline-block; text-decoration: none; background-color: #007bff; color: white; padding: 0.8rem 1.5rem; margin: 1.5rem 0; border: none; border-radius: 5px; font-family: 'Vazirmatn', sans-serif; font-size: 1.1rem; cursor: pointer; transition: background-color 0.3s; }
    .button:hover { background-color: #0056b3; }
    .center { text-align: center; }
    form { margin-top: 1.5rem; }
    .form-group { margin-bottom: 1rem; }
    .form-group label { display: block; margin-bottom: 0.5rem; font-weight: bold; }
    .form-group input, .form-group textarea { width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-family: 'Vazirmatn', sans-serif; }
    .timeline-container { margin-bottom: 2rem; }
    .timeline-bar { display: flex; width: 100%; height: 25px; background-color: #e9ecef; border-radius: 8px; overflow: hidden; border: 1px solid #dee2e6; }
    .timeline-segment { flex: 1; transition: background-color 0.5s ease, transform 0.2s ease; display: flex; align-items: center; justify-content: center; border-left: 1px solid rgba(255,255,255,0.5); position: relative; }
    .timeline-segment:first-child { border-left: none; }
    .timeline-segment.completed { background-color: #28a745; } /* Green */
    .timeline-segment.current { background-color: #007bff; transform: scale(1.05); z-index: 10; box-shadow: 0 0 10px rgba(0,123,255,0.5); } /* Blue */
    .timeline-segment.future { background-color: #e9ecef; } /* Grey */
    .timeline-label { color: white; font-weight: 500; font-size: 0.8rem; text-shadow: 1px 1px 1px rgba(0,0,0,0.2); opacity: 0; transition: opacity 0.3s; }
    .timeline-segment:hover .timeline-label { opacity: 1; }
    .timeline-segment.current .timeline-label { opacity: 1; }
    .timeline-segment.future .timeline-label { color: #6c757d; text-shadow: none; }
  </style>
</head>
<body>
  <div class="container">
    <div class="timeline-container">
        __TIMELINE_PLACEHOLDER__
    </div>
    <h1>{{ title }}</h1>
    __CONTENT_PLACEHOLDER__
  </div>
</body>
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
    timeline_html = generate_timeline_html(None) # No stage is active yet
    page_content = """
      <p style="text-align: center;">به آزمایش سیستم تدریس هوشمند مبتنی بر مدل‌های زبان بزرگ خوش آمدید.</p>
      <h2>مراحل آزمایش</h2>
      <ol style="list-style-type: none; padding-right: 20px;">
        <li style="margin-bottom:0.5rem;">۱. پرسشنامه سبک یادگیری (FSLSM)</li>
        <li style="margin-bottom:0.5rem;">۲. سه جلسه گفتگو با دستیار هوشمند که هر کدام با یک آزمون کوتاه دنبال می‌شود.</li>
        <li style="margin-bottom:0.5rem;">۳. پرسشنامه نهایی پس از آزمون</li>
      </ol>
      <div class="center">
        <a href="{{ url_for('fslsm_questionnaire') }}" class="button">شروع آزمایش</a>
      </div>
    """
    full_html = LAYOUT_HTML.replace("__TIMELINE_PLACEHOLDER__", timeline_html).replace("__CONTENT_PLACEHOLDER__", page_content)
    return render_template_string(full_html, title="به آزمایش خوش آمدید")

@app.route('/fslsm')
def fslsm_questionnaire():
    timeline_html = generate_timeline_html('fslsm')
    page_content = """
      <form id="quizForm" method="post" action="{{ url_for('submit_fslsm') }}">
        <div class="form-group">
          <label for="name">نام و نام خانوادگی (یا نام مستعار)</label>
          <input type="text" id="name" name="name" placeholder="مثال: مریم رضایی" required>
        </div>
        <div id="questions"></div>
        <div class="center">
            <button type="submit" id="submitBtn" class="button">ثبت و شروع گفتگو</button>
        </div>
      </form>
    <script>
        const questions = [
            { q: "۱) هنگامی مطلب را بهتر می فهمیم که:", a: "الف) آن را آزمایش می کنم.", b: "ب) درباره آن کاملاً فکر می کنم."}, { q: "۲) ترجیح می دهم:", a: "الف) واقع بین به نظر برسم.", b: "ب) مبتکر به نظر برسم."}, { q: "۳) وقتی به آنچه دیروز انجام داده ام فکر می کنم، بیشتر:", a: "الف) آن را به صورت تصویر به یاد می آورم.", b: "ب) آن را به صورت کلمات به یاد می آورم."}, { q: "۴) معمولاً:", a: "الف) جزئیات موضوع را می فهمم، اما درباره ساختار کلی آن گیج می شوم.", b: "ب) ساختار کلی موضوع را می فهمم، اما درباره جزئیات آن گیج می شوم."}, { q: "۵) برای یادگیری هر چیز تازه:", a: "الف) صحبت کردن درباره آن به من کمک می کند.", b: "ب) فکر کردن درباره آن به من کمک می کند."}, { q: "۶) اگر معلم شوم، ترجیح می دهم درسی بدهم که:", a: "الف) با حقایق زندگی سروکار داشته باشد.", b: "ب) با عقاید و نظریه ها سروکار داشته باشد."}, { q: "۷) ترجیح می دهم مطالب جدید را از طریق:", a: "الف) تصاویر، جدولها و نقشه ها یاد بگیرم.", b: "ب) دستورالعملهای مکتوب یا اطلاعات شفاهی یاد بگیرم."}, { q: "۸) وقتی:", a: "الف) همه اجزای مطلب را بفهمم، کل مطلب را می فهمم.", b: "ب) کل مطلب را بفهمم، همه اجزای آن را می فهمم."}, { q: "۹) در میان گروهی که مسئله دشواری را بررسی می کنند، من به احتمال زیاد:", a: "الف) وارد بحث می شوم و عقیده ام را بیان می کنم.", b: "ب) در گوشه ای می نشینم و گوش می دهم."}, { q: "۱۰) یادگیری:", a: "الف) واقعیات را آسان تر می دانم.", b: "ب) مفاهیم را آسان تر می دانم."}, { q: "۱۱) هنگام مطالعه کتابی که تصاویر و شکلهای بسیار زیادی دارد، به احتمال زیاد:", a: "الف) تصاویر و نمودارها را به دقت بررسی می کنم.", b: "ب) توجه خود را به نوشته های کتاب معطوف می کنم."}, { q: "۱۲) هنگام حل مسائل ریاضی:", a: "الف) معمولاً مرحله به مرحله روی راه حلهایی که به جواب می رسند کار می کنم.", b: "ب) غالباً ابتدا راه حلها را بررسی می کنم و سپس سعی می کنم مراحلی که برای رسیدن به آنها لازم است بیابم."}, { q: "۱۳) وقتی در کلاسی شرکت می کنم:", a: "الف) معمولاً با بسیاری از دانش آموزان آشنا می شوم.", b: "ب) معمولاً با تعداد کمی از دانش آموزان آشنا می شوم."}, { q: "۱۴) در مطالعه مطالب واقعی، ترجیح می دهم مطالب:", a: "الف) چیزهای جدیدی به من بیاموزند یا به من چگونگی انجام دادن کارها را یاد بدهند.", b: "ب) ایده های جدیدی برای فکر کردن درباره آنها در اختیار من بگذراند."}, { q: "۱۵) معلمانی را دوست دارم که هنگام درس دادن:", a: "الف) جدولها و نمودارهای زیادی روی تخته می کشند.", b: "ب) زمان زیادی را صرف توضیح دادن می کنند."}, { q: "۱۶) هنگام تحلیل داستان یا رمان:", a: "الف) به اتفاقات داستان فکر می کنم و می کوشم آنها را به منظور فهم موضوع اصلی داستان به یکدیگر مرتبط سازم.", b: "ب) چون وقتی که داستان را تمام می کنم فقط موضوع اصلی آن را به خاطر می آورم، باید به عقب برگردم و رابطه بین اتفاقهای داستان را پیدا کنم."}, { q: "۱۷) وقتی حل مسئله را شروع می کنم، به احتمال زیاد:", a: "الف) بلافاصله روی راه حل آن کار می کنم.", b: "ب) ابتدا سعی می کنم مسئله را کاملاً بفهمم."}, { q: "۱۸) بیشتر:", a: "الف) عقاید قطعی را ترجیح می دهم.", b: "ب) فرضیات را ترجیح می دهم."}, { q: "۱۹) آنچه را:", a: "الف) می بینم بهتر به یاد می آورم.", b: "ب) می شنوم بهتر به یاد می آورم."}, { q: "۲۰) برای من خیلی مهم است که معلم:", a: "الف) مطالب را با نظم و ترتیب روشن ارائه دهد.", b: "ب) تصویری کلی از مطالب را ارائه دهد و آن را با موضوعات دیگر مرتبط سازد."}, { q: "۲۱) ترجیح می دهم:", a: "الف) در گروه مطالعه کنم.", b: "ب) به تنهایی مطالعه کنم."}, { q: "۲۲) بیشتر ترجیح می دهم:", a: "الف) درباره جزئیات کار دقیق باشم.", b: "ب) در چگونگی انجام دادن کار خلاق باشم."}, { q: "۲۳) برای پیدا کردن محلی ناآشنا:", a: "الف) استفاده از نقشه را ترجیح می دهم.", b: "ب) استفاده از آدرس مکتوب را ترجیح می دهم."}, { q: "۲۴) مطالب را:", a: "الف) در مراحل نسبتاً منظم و با تلاش زیاد یاد می گیرم.", b: "ب) در ابتدا خوب نمی فهمم و کاملاً گیج می شوم، اما ناگهان آن را یاد می گیرم."}, { q: "۲۵) ترجیح می دهم ابتدا:", a: "الف) کارها را انجام دهم.", b: "ب) در باره چگونگی انجام دادن کارها فکر کنم."}, { q: "۲۶) وقتی برای سرگرمی مطالعه می کنم، نویسندگانی را ترجیح می دهم که:", a: "الف) به روشنی منظورشان را بیان می کنند.", b: "ب) مطالب را به روشهای جالب و خلاق بیان می کنند."}, { q: "۲۷) وقتی در کلاس تصویر یا شکلی می بینم، احتمال زیادی وجود دارد که:", a: "الف) تصویر یا شکل را به یاد بیاورم.", b: "ب) توضیحات معلم درباره تصویر یا شکل را به یاد بیاورم."}, { q: "۲۸) هنگامی که با اطلاعات زیادی مواجه می شوم به احتمال زیاد:", a: "الف) به جزئیات توجه می کنم و اصل مطلب را از دست می دهم.", b: "ب) سعی می کنم، قبل از پرداختن به جزئیات، اصل مطلب را بفهمم."}, { q: "۲۹) یادآوری:", a: "الف) آنچه را انجام داده ام آسان تر می دانم.", b: "ب) آنچه را درباره اش زیاد فکر کرده ام، آسان تر می دانم."}, { q: "۳۰) وقتی باید کاری انجام دهم، ترجیح می دهم:", a: "الف) برای انجام دادن آن در یکی از روشهای موجود مهارت کسب کنم.", b: "ب) روشهای جدیدی ابداع کنم و به کار گیرم."}, { q: "۳۱) وقتی فردی متنی به من نشان می دهد:", a: "الف) شکلها و تصاویر آن را ترجیح می دهم.", b: "ب) خلاصه متن و نتایج آن را ترجیح می دهم."}, { q: "۳۲) برای تدوین مقاله، به احتمال زیاد:", a: "الف) نگارش مقاله را از ابتدا شروع می کنم و با رعایت ترتیب بخشها ادامه می دهم.", b: "ب) بخشهای مختلف مقاله را بدون توجه به ترتیب آنها آماده و سپس مرتب می کنم."}, { q: "۳۳) وقتی باید با دیگران به صورت گروهی کار کنم، مایلم در آغاز:", a: "الف) هر یک از افراد گروه عقاید و نظرهایشان را مطرح کنند.", b: "ب) افراد عقاید خود را ابتدا به صورت انفرادی بررسی و سپس در گروه مطرح کنند."}, { q: "۳۴) به نظر من بالاترین تمجید آن است که فرد را:", a: "الف) معقول بدانیم.", b: "ب) دارای تخیل قوی بدانیم."}, { q: "۳۵) اگر افرادی را در میهمانی ملاقات کنم، احتمال زیادی وجود دارد که:", a: "الف) چهره آنها را به یاد بیاورم.", b: "ب) آنچه را درباره خودشان گفته اند به یاد بیاورم."}, { q: "۳۶) وقتی موضوع جدیدی یاد می گیرم، ترجیح می دهم:", a: "الف) بر آن متمرکز شوم و تا آنجا که می توانم درباره آن مطالبی یاد بگیرم.", b: "ب) آن موضوع را با موضعهای دیگر مرتبط کنم."}, { q: "۳۷) به نظر دیگران، من:", a: "الف) خوش برخورد به شمار می آیم.", b: "ب) خوددار به شمار می آیم."}, { q: "۳۸) دروسی را ترجیح می دهم که بر:", a: "الف) موضوعات عینی مانند واقعیات و اطلاعات متمرکز باشند.", b: "ب) موضوعات انتزاعی مانند مفاهیم و نظریه ها متمرکز باشند."}, { q: "۳۹) برای سرگرمی، ترجیح می دهم:", a: "الف) تلویزیون تماشا کنم.", b: "ب) کتاب بخوانم."}, { q: "۴۰) بعضی از معلمان درس خود را با خلاصه ای از موضوع مورد بحث شروع می کنند، این خلاصه ها برای من:", a: "الف) کمی مفید هستند.", b: "ب) بسیار مفید هستند."}, { q: "۴۱) وقتی تکلیف به صورت گروهی انجام می شود، اختصاص یک نمره برای کل گروه:", a: "الف) درست است.", b: "ب) درست نیست."}, { q: "۴۲) در محاسبات طولانی، تمایل به:", a: "الف) مرور تمامی مراحل و کنترل دقیق محاسبات دارم.", b: "ب) مرور تمامی مراحل و کنترل دقیق محاسبات ندارم و باید خود را مجبور به انجام دادن آن کنم."}, { q: "۴۳) تجسم مکانهایی که در آنها بوده ام برای من:", a: "الف) نسبتاً آسان، کامل و دقیق است.", b: "ب) دشوار، بدون جزئیات و بی دقت است."}, { q: "۴۴) هنگام حل مسائل به صورت گروهی، بیشتر مایلم:", a: "الف) در مورد مراحل حل مسئله فکر کنم.", b: "ب) درباره نتایج و کاربردهای احتمالی راه حلها فکر کنم."}
        ];
        const container = document.getElementById("questions");
        questions.forEach((q, i) => {
            const div = document.createElement("div");
            div.className = "form-group";
            div.innerHTML = `<h3>${q.q}</h3><div><label><input type="radio" name="q${i}" value="A" required> ${q.a}</label><label><input type="radio" name="q${i}" value="B" required> ${q.b}</label></div>`;
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
  <title>CITS - TELAB Chat</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Vazirmatn:wght@400;500;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root { --user-msg-bg: #007bff; --assistant-msg-bg: #f1f3f5; --app-bg: #ffffff; --chat-bg: #f8f9fa; }
    body{font-family:'Vazirmatn',Inter,Arial,sans-serif;background:var(--chat-bg);margin:0;padding:1rem;display:flex;justify-content:center; align-items:center; height:100vh; box-sizing: border-box;}
    #app{width:100%;max-width:900px;background:var(--app-bg);border-radius:12px;box-shadow:0 6px 24px rgba(0,0,0,0.08);overflow:hidden;display:flex;flex-direction:column;height:90vh}
    .chat-header{padding:1rem;border-bottom:1px solid #eee; background:var(--app-bg);}
    .header-content{display:flex;justify-content:space-between;align-items:center; margin-bottom: 1rem;}
    .header-info h3 {margin:0;}
    .header-actions { display: flex; gap: 10px; }
    .header-actions a { text-decoration: none; }
    #messages{flex:1;padding:1rem;overflow:auto; background:var(--chat-bg);}
    .message{display:flex; max-width:85%;margin-bottom:1rem; flex-shrink: 0;}
    .message-content { padding: 0.75rem 1.25rem; border-radius: 18px; line-height: 1.6; box-shadow: 0 1px 3px rgba(0,0,0,0.08);}
    .user { margin-left: auto; justify-content: flex-end; }
    .user .message-content { background: var(--user-msg-bg); color: white; border-bottom-left-radius: 4px; }
    .assistant { margin-right: auto; justify-content: flex-start; }
    .assistant .message-content { background: var(--assistant-msg-bg); color: #212529; border-bottom-right-radius: 4px; }
    #inputbar{display:flex;border-top:1px solid #eee;padding:0.75rem;gap:0.75rem; background:var(--app-bg); align-items: flex-end;}
    textarea{flex:1;padding:0.75rem;border-radius:18px;border:1px solid #ddd;resize:none; font-family:inherit; max-height: 150px; text-align: right;}
    button{border:none;border-radius:50%;cursor:pointer; display:flex; align-items:center;justify-content:center;transition: background-color 0.2s;}
    button#sendBtn { background-color: #007bff; color: white; width: 44px; height: 44px; flex-shrink: 0; }
    button#sendBtn:disabled { background-color: #ccc; }
    button#sendBtn svg { width: 24px; height: 24px; }
    button.next-step-btn, button#restartBtn { background-color: #6c757d; color: white; border-radius: 8px; padding: 0.6rem 0.9rem; font-family: 'Vazirmatn';}
    button.next-step-btn { background-color: #28a745; }
    /* Typing Indicator */
    .typing-indicator span { height:8px;width:8px;background-color:#999;border-radius:50%;display:inline-block;animation:bob 1.4s infinite ease-in-out both; }
    .typing-indicator span:nth-child(1){animation-delay:-0.32s} .typing-indicator span:nth-child(2){animation-delay:-0.16s}
    @keyframes bob{0%,80%,100%{transform:scale(0)}40%{transform:scale(1.0)}}
    /* --- Full Timeline CSS for Chat Page --- */
    .timeline-container { margin-bottom: 0; }
    .timeline-bar { display: flex; width: 100%; height: 25px; background-color: #e9ecef; border-radius: 8px; overflow: hidden; border: 1px solid #dee2e6; }
    .timeline-segment { flex: 1; transition: all 0.5s ease; display: flex; align-items: center; justify-content: center; border-left: 1px solid rgba(255,255,255,0.5); position: relative; }
    .timeline-segment:first-child { border-left: none; }
    .timeline-segment.completed { background-color: #28a745; }
    .timeline-segment.current { background-color: #007bff; transform: scale(1.05); z-index: 10; box-shadow: 0 0 10px rgba(0,123,255,0.5); }
    .timeline-segment.future { background-color: #e9ecef; }
    .timeline-label { color: white; font-weight: 500; font-size: 0.8rem; text-shadow: 1px 1px 1px rgba(0,0,0,0.2); opacity: 0; transition: opacity 0.3s; white-space: nowrap; }
    .timeline-segment:hover .timeline-label { opacity: 1; }
    .timeline-segment.current .timeline-label { opacity: 1; }
    .timeline-segment.future .timeline-label { color: #6c757d; text-shadow: none; }
  </style>
</head>
<body>
  <div id="app">
    <div class="chat-header">
        <div class="header-content">
            <div class="header-info">
              <h3 style="margin:0">آقای G</h3>
              <div id="meta" style="font-size:0.9rem;color:#666;margin-top:4px;"></div>
            </div>
            <div class="header-actions">
              {% if next_step_url %}<a href="{{ next_step_url }}"><button class="next-step-btn">{{ next_step_text }}</button></a>{% endif %}
              <button id="restartBtn">شروع مجدد</button>
            </div>
        </div>
        <div class="timeline-container">{{ timeline_html|safe }}</div>
    </div>
    <main id="messages"></main>
    <div id="inputbar">
      <textarea id="input" rows="1" placeholder="سوال خود را بنویسید..."></textarea>
      <button id="sendBtn" title="ارسال"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3.478 2.405a.75.75 0 0 0-.926.94l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.405Z" /></svg></button>
    </div>
  </div>
<script>
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
function addMessage(htmlContent, role) {
    const messageWrapper = document.createElement('div');
    messageWrapper.className = `message ${role}`;
    messageWrapper.innerHTML = `<div class="message-content">${htmlContent}</div>`;
    messagesEl.appendChild(messageWrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}
async function loadData(){
    const p_res = await fetch('/participant'); const p_data = await p_res.json();
    if(p_data.name) document.getElementById('meta').textContent = `شرکت‌کننده: ${p_data.name} | گروه: ${p_data.group}`;
    const h_res = await fetch('/history'); const h_data = await h_res.json();
    if(h_data.history) h_data.history.forEach(m => addMessage(marked.parse(m.content), m.role === 'user' ? 'user' : 'assistant'));
}
async function sendMessage() {
    const text = inputEl.value.trim(); if(!text) return;
    addMessage(marked.parse(text), 'user');
    inputEl.value=''; inputEl.style.height='auto'; sendBtn.disabled=true;
    const indicator = document.createElement('div');
    indicator.className = 'message assistant';
    indicator.innerHTML = `<div class="message-content typing-indicator"><span></span><span></span><span></span></div>`;
    messagesEl.appendChild(indicator);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    try {
        const res = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
        const data = await res.json();
        indicator.querySelector('.message-content').innerHTML = marked.parse(data.reply || '(no reply)');
    } catch(e){
        indicator.querySelector('.message-content').innerHTML = '**[خطای اتصال]** عدم موفقیت در ارتباط با سرور.';
    } finally {
        sendBtn.disabled=false; inputEl.focus();
    }
}
sendBtn.addEventListener('click', sendMessage);
inputEl.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
inputEl.addEventListener('input', () => { inputEl.style.height = 'auto'; inputEl.style.height = (inputEl.scrollHeight) + 'px'; });
document.getElementById('restartBtn').addEventListener('click', () => { if (confirm("آیا مطمئن هستید؟ تمام پیشرفت شما پاک خواهد شد.")) window.location.href = '/'; });
window.addEventListener('load', async () => { await loadData(); inputEl.focus(); });
</script>
</body></html>""", timeline_html=timeline_html, next_step_url=next_step_url, next_step_text=next_step_text)

# --- Other Routes (exam, post_test, etc.) ---
@app.route('/exam/<int:exam_id>')
@participant_required
def exam(exam_id):
    current_stage = get_stage()
    expected_chat_stage = f'chat{exam_id}'
    expected_exam_stage = f'exam{exam_id}'

    if current_stage == expected_chat_stage:
        set_stage(expected_exam_stage)
        current_stage = expected_exam_stage

    if current_stage != expected_exam_stage:
        return redirect(url_for('chat_page') if 'chat' in str(get_stage()) else 'homepage')

    timeline_html = generate_timeline_html(current_stage)
    page_content = """
      <p>لطفا به سوالات زیر پاسخ دهید. پس از اتمام، روی دکمه زیر کلیک کنید.</p>
      <form method="post" action="{{ url_for('submit_exam', exam_id=exam_id) }}">
        <div class="form-group">
            <label for="q1">سوال اول آزمون {{ exam_id }} در اینجا قرار می‌گیرد.</label>
            <textarea name="q1" rows="4"></textarea>
        </div>
        <div class="form-group">
            <label for="q2">سوال دوم آزمون {{ exam_id }} در اینجا قرار می‌گیرد.</label>
            <textarea name="q2" rows="4"></textarea>
        </div>
        <div class="center">
          <button type="submit" class="button">ثبت آزمون و ادامه</button>
        </div>
      </form>
    """
    full_html = LAYOUT_HTML.replace("__TIMELINE_PLACEHOLDER__", timeline_html).replace("__CONTENT_PLACEHOLDER__", page_content)
    return render_template_string(full_html, title=f"آزمون شماره {exam_id}", exam_id=exam_id)

@app.route('/submit_exam/<int:exam_id>', methods=['POST'])
@participant_required
def submit_exam(exam_id):
    if exam_id == 3:
        set_stage('post_test')
        return redirect(url_for('post_test'))
    else:
        set_stage(f'chat{exam_id + 1}')
        return redirect(url_for('chat_page'))

@app.route('/post_test')
@participant_required
def post_test():
    if get_stage() != 'post_test': return redirect(url_for('homepage'))
    timeline_html = generate_timeline_html('post_test')
    page_content = """
      <p>لطفاً برای تکمیل آزمایش، به سوالات زیر درباره تجربه خود پاسخ دهید.</p>
      <form method="post" action="{{ url_for('submit_post_test') }}">
        <div class="form-group">
            <label>۱. به طور کلی، دستیار هوشمند چقدر در یادگیری به شما کمک کرد؟ (۱=خیلی کم، ۵=خیلی زیاد)</label>
            <input type="range" name="q1_rating" min="1" max="5" value="3" style="width:100%">
        </div>
        <div class="form-group">
            <label for="q2_feedback">۲. چه چیزی را در مورد تعامل با دستیار هوشمند بیشتر دوست داشتید؟</label>
            <textarea name="q2_feedback" rows="4"></textarea>
        </div>
        <div class="center"> <button type="submit" class="button">پایان آزمایش</button> </div>
      </form>
    """
    full_html = LAYOUT_HTML.replace("__TIMELINE_PLACEHOLDER__", timeline_html).replace("__CONTENT_PLACEHOLDER__", page_content)
    return render_template_string(full_html, title="پرسشنامه نهایی")


@app.route('/submit_post_test', methods=['POST'])
@participant_required
def submit_post_test():
    set_stage('end')
    return redirect(url_for('end_page'))

@app.route('/end')
def end_page():
    timeline_html = generate_timeline_html('end')
    page_content = """
      <h2 style="color: #28a745;">آزمایش با موفقیت به پایان رسید.</h2>
      <p style-align: center;">از مشارکت شما در این تحقیق بسیار سپاسگزاریم. اکنون می‌توانید این صفحه را ببندید.</p>
    """
    full_html = LAYOUT_HTML.replace("__TIMELINE_PLACEHOLDER__", timeline_html).replace("__CONTENT_PLACEHOLDER__", page_content)
    session.clear() # Clear the session at the very end
    return render_template_string(full_html, title="پایان آزمایش")


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