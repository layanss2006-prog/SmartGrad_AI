# دليل نشر SmartGrad AI على PythonAnywhere

المجلد الجذر للمشروع في بيئة العمل الحالية هو:

```text
/home/YOUR_USERNAME/SmartGrad_AI
```

استبدل `YOUR_USERNAME` باسم حسابك على PythonAnywhere.

## 1. إنشاء حساب PythonAnywhere

1. أنشئ حساباً على PythonAnywhere.
2. افتح تبويب `Files`.
3. افتح تبويب `Consoles` وأنشئ Bash console.

## 2. رفع المشروع

باستخدام Git إذا كان المشروع في مستودع:

```bash
cd ~
git clone https://YOUR_GIT_REPOSITORY_URL.git SmartGrad_AI
cd SmartGrad_AI
```

إذا كنت سترفع الملفات يدوياً، ارفع المجلد داخل:

```text
/home/YOUR_USERNAME/SmartGrad_AI
```

لا ترفع مجلدات `.venv` أو `__pycache__` أو ملفات `.env` إذا رفعت المشروع بدون Git.

لحفظ بيانات SQLite الحالية، ارفع ملف `db.sqlite3` إلى جذر المشروع قبل تنفيذ migrations، دون استبداله بملف فارغ.

## 3. إنشاء Virtual Environment وتثبيت المكتبات

في Bash:

```bash
cd /home/YOUR_USERNAME/SmartGrad_AI
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

إذا كانت PythonAnywhere لا توفر Python 3.11 في حسابك، اختر إصداراً متاحاً من لوحة Python عبر 3.10 على الأقل.

## 4. إعداد متغيرات البيئة

أنشئ ملف `.env` داخل جذر المشروع:

```bash
cd /home/YOUR_USERNAME/SmartGrad_AI
nano .env
```

استخدم القيم التالية:

```env
SECRET_KEY=ضع-هنا-مفتاحاً-عشوائياً-طويلاً
DEBUG=False
ALLOWED_HOSTS=YOUR_USERNAME.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://YOUR_USERNAME.pythonanywhere.com
SQLITE_DB_PATH=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
REDIS_URL=
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
```

لا تضع `.env` في مستودع Git ولا تنشر مفاتيح API.

يمكن إنشاء `SECRET_KEY` بالأمر التالي:

```bash
source .venv/bin/activate
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

ضع الناتج في `SECRET_KEY`.

إذا كنت تريد استخدام نموذج خارجي، ضع مفتاح OpenAI في `OPENAI_API_KEY`. وإلا اتركه فارغاً وسيعمل النظام بالتحليل المحلي الاحتياطي.

## 5. إعداد Web App

في تبويب `Web` في PythonAnywhere:

1. اضغط `Add a new web app`.
2. اختر النطاق `YOUR_USERNAME.pythonanywhere.com`.
3. اختر `Manual configuration`.
4. اختر Python 3.11 أو الإصدار المستخدم عند إنشاء Virtual Environment.

في قسم `Virtualenv` أدخل:

```text
/home/YOUR_USERNAME/SmartGrad_AI/.venv
```

في قسم `Source code` أدخل:

```text
/home/YOUR_USERNAME/SmartGrad_AI
```

في قسم `WSGI configuration file` افتح الملف المحدد من PythonAnywhere واستبدل محتواه بما يلي:

```python
import os
import sys

project_home = "/home/YOUR_USERNAME/SmartGrad_AI"

if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

يجب أن يكون اسم ملف المشروع بعد جذر المسار هو `config.settings`، لأن مجلد الإعدادات الفعلي هو:

```text
SmartGrad_AI/config/
```

## 6. إعداد قاعدة البيانات والملفات الثابتة

من Bash console:

```bash
cd /home/YOUR_USERNAME/SmartGrad_AI
source .venv/bin/activate

python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput
```

إذا رفعت قاعدة بيانات موجودة، نفذ migrations فقط لتحديث هيكلها. لا تستخدم `flush` ولا احذف `db.sqlite3`.

لعرض حسابات البيانات الموجودة، افتح Django shell:

```bash
python manage.py shell
```

إنشاء مدير:

```bash
python manage.py createsuperuser
```

في تبويب `Web` ضمن `Static files` أضف:

| URL | Directory |
|---|---|
| `/static/` | `/home/YOUR_USERNAME/SmartGrad_AI/staticfiles/` |
| `/media/` | `/home/YOUR_USERNAME/SmartGrad_AI/media/` |

تحذير: PythonAnywhere لا يعرض مجلدات media دائماً من الإعدادات وحدها؛ يجب إنشاء mapping في تبويب Web.

لتبسيط تدقيق الصور والشعارات، أضف على وجه الخصوص:

```text
/static/css/style.css
/static/images/smartgrad-logo.png
/static/images/smartgrad-brand.png
```

## 7. إعادة التحميل والاختبار

بعد حفظ إعدادات WSGI وStatic files اضغط `Reload` في تبويب `Web`.

اختبر المسارات:

- `/`
- `/home/`
- `/welcome/`
- `/projects/`
- `/about/`
- `/accounts/login/`
- `/register/`
- `/admin/`

تحقق أيضاً من:

- تحميل CSS والشعارات.
- تسجيل الدخول والتسجيل.
- إنشاء مجموعة وإضافة مهمة وتحديث حالتها.
- رفع وتسليم الملفات.
- ظهور تاريخ البدء والمواعيد النهائية.
- عمل الإشعارات المخزنة.

## 8. قيود خدمة PythonAnywhere

SQLite مناسب للحسابات الصغيرة والبيانات النموذجية، لكنه ليس الخيار الأفضل لأحمال الكتابة المتزامنة أو النسخ الاحتياطي السريع. لا تفصح معلومات حساسة داخل قاعدة البيانات ولا تشارك ملف قاعدة البيانات علناً.

الإشعارات اللحظية والمحادثة الحالية تستخدم Django Channels وWebSocket عبر `daphne`/ASGI. لا تدعم خطط PythonAnywhere المجانية غالباً WebSocket الطويل؛ قد تظل الإشعارات المخزنة والمحاضر والتحديثات عند إعادة تحميل الصفحة تعمل عبر WSGI. للاستخدام الكامل، يلزم خطة تدعم ASGI وعملية قابلة للاستمرار أو خدمة خارجية للـ WebSocket.

لا يوجد Redis مطلوب للتشغيل الأساسي؛ مع `REDIS_URL=` يستخدم المشروع InMemoryChannelLayer المناسب للتطوير أو عملية واحدة.
