import os
import logging
import asyncio
import feedparser
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    MessageHandler, filters
)
import google.generativeai as genai

# ───────────────────────────────────────────────
# إعدادات التسجيل
# ───────────────────────────────────────────────
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────
# المفاتيح من متغيرات البيئة
# ───────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@IioIio059")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

if not GEMINI_API_KEY or not BOT_TOKEN:
    raise ValueError("❌ يجب تعيين متغيرات البيئة GEMINI_API_KEY و BOT_TOKEN")

genai.configure(api_key=GEMINI_API_KEY)
# تم تعديل النموذج هنا ليعمل مباشرة بدون أخطاء
model = genai.GenerativeModel('gemini-3.6-flash')


# ───────────────────────────────────────────────
# الإعدادات العامة
# ───────────────────────────────────────────────
NEWS_CHECK_INTERVAL = 3600  # كل ساعة
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q=wwe+aew+njpw+tna+roh+wrestling+news&hl=en-US&gl=US&ceid=US:en"

last_published_title = None

# ───────────────────────────────────────────────
# دالة جلب أحدث خبر من جوجل
# ───────────────────────────────────────────────
def get_google_news():
    try:
        feed = feedparser.parse(GOOGLE_NEWS_RSS)
        if feed.entries:
            latest = feed.entries[0]
            return {
                "title": latest.title,
                "link": latest.link,
                "summary": latest.get("summary", latest.title),
                "published": latest.get("published", "غير معروف")
            }
    except Exception as e:
        logger.error(f"خطأ في جلب أخبار جوجل: {e}")
    return None

# ───────────────────────────────────────────────
# الأوامر المتاحة
# ───────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤖 أهلاً بك في بوت أخبار المصارعة الشامل!\n\n"
        "📰 **الأوامر المتاحة:**\n"
        "/news — جلب ونشر آخر خبر فوراً\n"
        "/wwe — جلب أخبار WWE\n"
        "/aew — جلب أخبار AEW\n"
        "/njpw — جلب أخبار NJPW\n"
        "/tna — جلب أخبار TNA\n"
        "/status — حالة البوت والنشر التلقائي\n"
        "/help — عرض هذه الرسالة\n\n"
        "📎 **يمكنك أيضاً إرسال:**\n"
        "• نص → يُصاغ ويُنشر\n"
        "• صورة + تعليق → يُنشر في القناة\n"
        "• فيديو + تعليق → يُنشر في القناة\n"
        "• صوت/تسجيل صوتي → يُنشر في القناة\n\n"
        "⏰ النشر التلقائي يعمل كل ساعة لجميع الاتحادات."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_text = (
        f"📊 **حالة البوت:**\n"
        f"🕐 الوقت الحالي: {now}\n"
        f"📡 النشر التلقائي: كل {NEWS_CHECK_INTERVAL // 60} دقيقة\n"
        f"📰 آخر خبر منشور: {last_published_title or 'لم يُنشر بعد'}\n"
        f"✅ البوت يعمل بشكل طبيعي."
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري جلب آخر خبر من أخبار جوجل...")
    news_item = get_google_news()
    if not news_item:
        await update.message.reply_text("❌ لم أتمكن من جلب الأخبار حالياً، جرب لاحقاً.")
        return

    prompt = f"""
أنت محرر صحفي رياضي خبير ومختص في رصد أخبار جميع اتحادات المصارعة الحرة في العالم.
قم بقراءة هذا الخبر القادم من أخبار جوجل وترجمته وصياغته بأسلوب صحفي جذّاب:
العنوان الأصلي: {news_item['title']}
التزم حرفياً بهذا القالب المستقل:
🔴 **[عنوان الخبر باللغة العربية]**
[التفاصيل والتلخيص بأسلوب صحفي محترف ومختصر]
🔗 **المصدر:** [أخبار جوجل (اضغط هنا)]({news_item['link']})
🏷️ **التصنيف:** [عاجل / تقرير] | **اتحاد:** [اكتب اسم الاتحاد الصحيح بدقة، مثل #WWE أو #AEW]
"""
    try:
        response = model.generate_content(prompt)
        news_text = response.text
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=news_text,
            parse_mode="Markdown",
            disable_web_page_preview=False
        )
        global last_published_title
        last_published_title = news_item['title']
        await update.message.reply_text("✅ تم نشر الخبر في القناة!")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في النشر: {e}")

async def wwe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await fetch_specific_news(update, context, "WWE")

async def aew_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await fetch_specific_news(update, context, "AEW")

async def njpw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await fetch_specific_news(update, context, "NJPW")

async def tna_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await fetch_specific_news(update, context, "TNA")

async def fetch_specific_news(update: Update, context: ContextTypes.DEFAULT_TYPE, federation: str):
    await update.message.reply_text(f"⏳ جاري البحث عن أخبار {federation}...")
    rss_url = f"https://news.google.com/rss/search?q={federation}+wrestling+news&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            await update.message.reply_text(f"❌ لم أجد أخبار {federation} حالياً.")
            return
        latest = feed.entries[0]
        news_item = {
            "title": latest.title,
            "link": latest.link,
            "summary": latest.get("summary", latest.title),
            "published": latest.get("published", "غير معروف")
        }
        prompt = f"""
أنت محرر صحفي رياضي خبير ومختص في رصد أخبار جميع اتحادات المصارعة الحرة.
ركّز بشكل خاص على اتحاد {federation} في هذا الخبر.
العنوان الأصلي: {news_item['title']}
التزم حرفياً بهذا القالب:
🔴 **[عنوان الخبر باللغة العربية]**
[التفاصيل والتلخيص بأسلوب صحفي محترف ومختصر]
🔗 **المصدر:** [اضغط هنا]({news_item['link']})
🏷️ **التصنيف:** [عاجل / تقرير] | **اتحاد:** [#{federation}]
"""
        response = model.generate_content(prompt)
        news_text = response.text
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=news_text,
            parse_mode="Markdown",
            disable_web_page_preview=False
        )
        await update.message.reply_text(f"✅ تم نشر خبر {federation}!")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    caption_text = message.caption if message.caption else message.text
    if not message.photo and not message.video and not message.audio and not message.voice and caption_text:
        lower_text = caption_text.lower().strip()
        if any(w in lower_text for w in ["خبر", "جديد", "آخر", "news"]):
            await news_command(update, context)
            return
        elif any(w in lower_text for w in ["wwe", "دبليو"]):
            await wwe_command(update, context)
            return
        elif any(w in lower_text for w in ["aew", "اي اي"]):
            await aew_command(update, context)
            return
        elif any(w in lower_text for w in ["njpw", "ان جاي"]):
            await njpw_command(update, context)
            return
        elif any(w in lower_text for w in ["tna", "تي ان اي"]):
            await tna_command(update, context)
            return
        elif any(w in lower_text for w in ["حالة", "status", "شغال"]):
            await status_command(update, context)
            return

    if not caption_text:
        caption_text = "تغطية خاصة لأبرز مستجدات المصارعة الحرة."

    prompt = f"""
أنت محرر صحفي رياضي محترف. قم بصياغة المحتوى التالي ليظهر كـ "خبر مستقل ومنظم":
🔴 **[عنوان الخبر بأسلوب جذاب]**
[تفاصيل الخبر بصياغة احترافية وباللغة العربية]
🏷️ **التصنيف:** [عاجل / تقرير] | **اتحاد:** [#اسم_الاتحاد]
المحتوى المطلوب صياغته: {caption_text}
"""
    try:
        response = model.generate_content(prompt)
        ai_reply = response.text
        if message.photo:
            photo_file = await message.photo[-1].get_file()
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo_file.file_path, caption=ai_reply, parse_mode="Markdown")
        elif message.video:
            video_file = await message.video.get_file()
            await context.bot.send_video(chat_id=CHANNEL_ID, video=video_file.file_path, caption=ai_reply, parse_mode="Markdown")
        elif message.audio or message.voice:
            audio_obj = message.audio if message.audio else message.voice
            audio_file = await audio_obj.get_file()
            await context.bot.send_audio(chat_id=CHANNEL_ID, audio=audio_file.file_path, caption=ai_reply, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=ai_reply, parse_mode="Markdown")
        await message.reply_text("✅ تمت الصياغة والنشر في القناة بنجاح!")
    except Exception as e:
        logger.error(f"خطأ في معالجة الرسالة: {e}")
        await message.reply_text(f"❌ حدث خطأ أثناء النشر: {e}")

async def automated_news_loop(context: ContextTypes.DEFAULT_TYPE):
    global last_published_title
    while True:
        try:
            news_item = get_google_news()
            if news_item:
                if news_item['title'] == last_published_title:
                    logger.info("الخبر نفسه تم نشره مسبقاً، سيتم التخطي.")
                else:
                    prompt = f"""
أنت محرر صحفي رياضي خبير ومختص في رصد أخبار جميع اتحادات المصارعة الحرة.
العنوان الأصلي: {news_item['title']}
التزم حرفياً بهذا القالب المستقل:
🔴 **[عنوان الخبر باللغة العربية]**
[التفاصيل والتلخيص بأسلوب صحفي محترف ومختصر]
🔗 **المصدر:** [أخبار جوجل (اضغط هنا)]({news_item['link']})
🏷️ **التصنيف:** [عاجل / تقرير] | **اتحاد:** [اكتب اسم الاتحاد الصحيح بدقة]
"""
                    response = model.generate_content(prompt)
                    news_text = response.text
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=news_text,
                        parse_mode="Markdown",
                        disable_web_page_preview=False
                    )
                    last_published_title = news_item['title']
                    logger.info("تم جلب ونشر الخبر التلقائي لكافة الاتحادات بنجاح.")
            else:
                logger.warning("⚠️ لم يتم العثور على أخبار جديدة.")
        except Exception as e:
            logger.error(f"خطأ في حلقة النشر التلقائي: {e}")
        await asyncio.sleep(NEWS_CHECK_INTERVAL)

async def post_init(application):
    asyncio.create_task(automated_news_loop(application))

def main():
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("news", news_command))
    application.add_handler(CommandHandler("wwe", wwe_command))
    application.add_handler(CommandHandler("aew", aew_command))
    application.add_handler(CommandHandler("njpw", njpw_command))
    application.add_handler(CommandHandler("tna", tna_command))
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE) & (~filters.COMMAND), handle_user_input))
    
    logger.info("🚀 البوت يعمل الآن بكامل الميزات...")
    application.run_polling()

if __name__ == '__main__':
    main()
