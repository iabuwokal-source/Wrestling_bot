#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🥊 وكالة أخبار الرياضات القتالية والنزالات العالمية الشاملة
Ultimate Combat Sports & Pro Wrestling News Agency Bot
═══════════════════════════════════════════════════════════════
ملف واحد شامل - جاهز للنسخ واللصق مباشرة
"""

import os
import sys
import asyncio
import sqlite3
import logging
import re
import json
import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# ── Telegram ──
from telegram import Bot
from telegram.constants import ParseMode

# ── Gemini AI ──
import google.generativeai as genai

# ═══════════════════════════════════════════════════════════════
# 🔑 الإعدادات الأساسية
# ═══════════════════════════════════════════════════════════════

GEMINI_API_KEY = "AQ.Ab8RN6KUY4IIZbkZDmmebEUgPD8uYsQKaR76PhP4u0_PYpKxUg"
TELEGRAM_BOT_TOKEN = "8980137931:AAFNUMuyRNT0mHUyD0bXzJggBlRtxRQ4_hQ"
TELEGRAM_CHANNEL_ID = "@IioIio059"

# روابط RSS
RSS_FEEDS = {
    "wrestling": [
        "https://news.google.com/rss/search?q=WWE+AEW+Pro+Wrestling+news&hl=en-US&gl=US&ceid=US:en",
    ],
    "mma": [
        "https://news.google.com/rss/search?q=UFC+PFL+Bellator+MMA+news&hl=en-US&gl=US&ceid=US:en",
    ],
    "boxing": [
        "https://news.google.com/rss/search?q=WBC+WBA+IBF+WBO+Boxing+news&hl=en-US&gl=US&ceid=US:en",
    ],
    "kickboxing": [
        "https://news.google.com/rss/search?q=Glory+Kickboxing+Karate+Judo+news&hl=en-US&gl=US&ceid=US:en",
    ],
}

# كلمات مفتاحية للتصفية
REQUIRED_KEYWORDS = [
    "wwe", "aew", "nxt", "raw", "smackdown", "dynamite", "collision",
    "tnn", "roh", "mlw", "nwa", "gcw", "njpw", "stardom", "aaa", "cmll",
    "wrestling", "wrestler", "champion", "title match", "pay-per-view", "ppv",
    "wrestlemania", "royal rumble", "summerslam", "survivor series",
    "ufc", "mma", "pfl", "bellator", "one championship", "rizin", "bkfc",
    "mixed martial arts", "knockout", "tko", "submission", "title fight",
    "boxing", "wbc", "wba", "ibf", "wbo", "heavyweight", "middleweight",
    "lightweight", "welterweight", "title bout", "championship fight",
    "kickboxing", "glory", "karate", "judo", "muay thai", "taekwondo",
    "k-1", "glory kickboxing",
]

EXCLUDED_KEYWORDS = [
    "porn", "xxx", "casino", "betting", "gambling", "crypto scam",
    "forex", "make money", "click here", "weight loss", "dating",
]

# التوقيتات
FETCH_INTERVAL_MINUTES = 30
PUBLISH_INTERVAL_MINUTES = 5
MAX_QUEUE_SIZE = 50
MAX_DAILY_POSTS = 100

# Gemini
GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_TEMPERATURE = 0.7
GEMINI_MAX_OUTPUT_TOKENS = 800

# المسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bot_database.db")
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

# قالب الرسالة
MESSAGE_TEMPLATE = """🔥 <b>{title}</b>

{content}

🔗 <b>المصدر الرسمي:</b> <a href="{url}">اضغط هنا للقراءة الكاملة</a>
🏷️ <b>التصنيف:</b> {hashtags}
"""

# ═══════════════════════════════════════════════════════════════
# 🗄️ قاعدة البيانات
# ═══════════════════════════════════════════════════════════════

class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS published_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    link TEXT UNIQUE NOT NULL,
                    title TEXT,
                    category TEXT,
                    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    link TEXT UNIQUE NOT NULL,
                    title TEXT,
                    summary TEXT,
                    category TEXT,
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed BOOLEAN DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE NOT NULL,
                    posts_count INTEGER DEFAULT 0,
                    fetched_count INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS error_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_message TEXT,
                    context TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def is_link_published(self, link: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM published_links WHERE link = ?", (link,))
            return cursor.fetchone() is not None

    def add_published_link(self, link: str, title: str = "", category: str = ""):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO published_links (link, title, category) VALUES (?, ?, ?)",
                    (link, title, category)
                )
                conn.commit()
        except Exception:
            pass

    def clean_old_links(self, days: int = 30):
        cutoff_date = datetime.now() - timedelta(days=days)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM published_links WHERE published_at < ?",
                (cutoff_date.isoformat(),)
            )
            conn.commit()
            return cursor.rowcount

    def add_to_queue(self, link: str, title: str, summary: str = "",
                     category: str = "", image_url: str = "") -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM news_queue WHERE processed = 0")
                count = cursor.fetchone()[0]
                if count >= MAX_QUEUE_SIZE:
                    return False
                cursor.execute(
                    "INSERT OR IGNORE INTO news_queue (link, title, summary, category, image_url) VALUES (?, ?, ?, ?, ?)",
                    (link, title, summary, category, image_url)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    def get_next_from_queue(self) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM news_queue WHERE processed = 0 ORDER BY created_at ASC LIMIT 1"
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def mark_queue_item_processed(self, item_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE news_queue SET processed = 1 WHERE id = ?", (item_id,))
            conn.commit()

    def get_queue_size(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM news_queue WHERE processed = 0")
            return cursor.fetchone()[0]

    def clear_processed_queue(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM news_queue WHERE processed = 1")
            conn.commit()
            return cursor.rowcount

    def get_today_posts_count(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT posts_count FROM daily_stats WHERE date = ?", (today,))
            row = cursor.fetchone()
            return row[0] if row else 0

    def increment_today_posts(self):
        today = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO daily_stats (date, posts_count) VALUES (?, 1) ON CONFLICT(date) DO UPDATE SET posts_count = posts_count + 1",
                (today,)
            )
            conn.commit()

    def log_error(self, error_message: str, context: str = ""):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO error_log (error_message, context) VALUES (?, ?)",
                    (str(error_message), context)
                )
                conn.commit()
        except:
            pass


# ═══════════════════════════════════════════════════════════════
# 📡 جلب الأخبار
# ═══════════════════════════════════════════════════════════════

class NewsFetcher:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def fetch_all_feeds(self) -> List[Dict]:
        all_news = []
        for category, feeds in RSS_FEEDS.items():
            for feed_url in feeds:
                try:
                    news_items = self._fetch_single_feed(feed_url, category)
                    all_news.extend(news_items)
                except Exception as e:
                    logging.warning(f"خطأ في جلب {feed_url}: {e}")

        seen_links = set()
        unique_news = []
        for item in all_news:
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                unique_news.append(item)

        return unique_news

    def _fetch_single_feed(self, feed_url: str, category: str) -> List[Dict]:
        feed = feedparser.parse(feed_url)
        news_items = []

        for entry in feed.entries[:20]:
            link = entry.get("link", "")
            title = entry.get("title", "")

            if self.db.is_link_published(link):
                continue

            if not self._is_relevant(title, entry.get("summary", "")):
                continue

            image_url = self._extract_image(entry)
            summary = entry.get("summary", "")

            if not summary and link:
                summary = self._fetch_article_summary(link)

            summary = self._clean_html(summary)

            news_items.append({
                "link": link,
                "title": title,
                "summary": summary[:500] if summary else title,
                "category": category,
                "image_url": image_url,
                "published": entry.get("published", ""),
            })

        return news_items

    def _is_relevant(self, title: str, summary: str = "") -> bool:
        text = f"{title} {summary}".lower()

        for keyword in EXCLUDED_KEYWORDS:
            if keyword.lower() in text:
                return False

        for keyword in REQUIRED_KEYWORDS:
            if keyword.lower() in text:
                return True

        return False

    def _extract_image(self, entry) -> Optional[str]:
        if "media_content" in entry:
            for media in entry.media_content:
                if media.get("medium") == "image" or media.get("type", "").startswith("image"):
                    return media.get("url")

        if "media_thumbnail" in entry:
            return entry.media_thumbnail[0].get("url")

        if "enclosures" in entry and entry.enclosures:
            for enc in entry.enclosures:
                if enc.get("type", "").startswith("image"):
                    return enc.get("href")

        link = entry.get("link", "")
        if link:
            return self._fetch_article_image(link)

        return None

    def _fetch_article_image(self, url: str) -> Optional[str]:
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")

            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                return og_image["content"]

            tw_image = soup.find("meta", attrs={"name": "twitter:image"})
            if tw_image and tw_image.get("content"):
                return tw_image["content"]

            return None
        except:
            return None

    def _fetch_article_summary(self, url: str) -> str:
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")

            article = soup.find("article") or soup.find("div", class_="article-content")

            if article:
                paragraphs = article.find_all("p")
                text = " ".join([p.get_text() for p in paragraphs[:3]])
                return text[:800]

            paragraphs = soup.find_all("p")
            text = " ".join([p.get_text() for p in paragraphs[:3]])
            return text[:800]

        except:
            return ""

    def _clean_html(self, text: str) -> str:
        if not text:
            return ""

        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator=" ", strip=True)


# ═══════════════════════════════════════════════════════════════
# 🤖 توليد المحتوى بالعربية (Gemini)
# ═══════════════════════════════════════════════════════════════

class ContentGenerator:
    def __init__(self, db: DatabaseManager):
        self.db = db
        genai.configure(api_key=GEMINI_API_KEY)

        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config={
                "temperature": GEMINI_TEMPERATURE,
                "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
            }
        )

    def generate_news_post(self, news_item: Dict) -> Optional[Dict]:
        try:
            title = news_item.get("title", "")
            summary = news_item.get("summary", "")
            category = news_item.get("category", "general")
            link = news_item.get("link", "")

            arabic_title = self._generate_title(title, summary)
            arabic_content = self._generate_content(title, summary, category)
            hashtags = self._generate_hashtags(title, summary, category)

            return {
                "title": arabic_title,
                "content": arabic_content,
                "hashtags": hashtags,
                "url": link,
                "image_url": news_item.get("image_url"),
                "category": category,
            }

        except Exception as e:
            logging.error(f"خطأ في توليد المحتوى: {e}")
            self.db.log_error(str(e), "generate_news_post")
            return None

    def _generate_title(self, english_title: str, summary: str) -> str:
        prompt = f"""أنت محرر صحفي رياضي عربي متخصص في الرياضات القتالية.

اكتب عنواناً صحفياً مثيراً ومشوقاً باللغة العربية الفصحى لهذا الخبر.
اجعله جذاباً ويستفز فضول القارئ. استخدم إيموجي مناسب.

العنوان الأصلي: {english_title}
الملخص: {summary[:300]}

قواعد:
- استخدم العربية الفصحى
- اجعله مثيراً ومشوقاً
- كحد أقصى 15 كلمة
- أرجع العنوان فقط بدون أي شيء آخر

العنوان العربي:"""

        try:
            response = self.model.generate_content(prompt)
            title = response.text.strip()
            title = re.sub(r'\*+', '', title)
            title = title.strip('"').strip("'")
            return title

        except Exception as e:
            logging.warning(f"خطأ في توليد العنوان: {e}")
            return f"🔥 خبر عاجل: {english_title[:80]}"

    def _generate_content(self, english_title: str, summary: str, category: str) -> str:
        category_names = {
            "wrestling": "المصارعة الحرة",
            "mma": "الفنون القتالية المختلطة (MMA)",
            "boxing": "الملاكمة",
            "kickboxing": "الكيك بوكسينغ والفنون القتالية",
        }

        cat_name = category_names.get(category, "الرياضات القتالية")

        prompt = f"""أنت صحفي رياضي محترف في وكالة أخبار الرياضات القتالية.

أعد صياغة هذا الخبر باللغة العربية الفصحى بأسلوب صحفي مشوق ومثير.

التصنيف: {cat_name}
العنوان الأصلي: {english_title}
الملخص: {summary[:500]}

متطلبات:
- اكتب بالعربية الفصحى بأسلوب صحفي جذاب ومشوق
- اذكر أسماء المصارعين/المقاتلين المذكورين
- اذكر الاتحاد/المنظمة (UFC, WWE, AEW, إلخ)
- بين 80 إلى 150 كلمة
- لا تضف رابط المصدر أو الهاشتاغات
- لا تستخدم تنسيق markdown مثل **غامق**

المحتوى العربي:"""

        try:
            response = self.model.generate_content(prompt)
            content = response.text.strip()
            content = re.sub(r'\*+', '', content)
            content = re.sub(r'#+', '', content)
            return content

        except Exception as e:
            logging.warning(f"خطأ في توليد المحتوى: {e}")
            return f"تقرير حصرى: {english_title}\n\n{summary[:300]}"

    def _generate_hashtags(self, title: str, summary: str, category: str) -> str:
        base_hashtags = {
            "wrestling": "#أخبار_المصارعة #WWE #AEW #المصارعة_الحرة",
            "mma": "#أخبار_القتال #UFC #MMA #فنون_قتالية",
            "boxing": "#أخبار_الملاكمة #Boxing #ملاكمة_عالمية",
            "kickboxing": "#أخبار_القتال #Kickboxing #فنون_قتالية",
        }

        extra_tags = []
        text = f"{title} {summary}".lower()

        if "ufc" in text:
            extra_tags.append("#UFC")

        if "wwe" in text:
            extra_tags.append("#WWE")

        if "aew" in text:
            extra_tags.append("#AEW")

        if "boxing" in text or "wbc" in text or "wba" in text:
            extra_tags.append("#ملاكمة")

        if "champion" in text or "title" in text:
            extra_tags.append("#بطولة")

        if "knockout" in text or "tko" in text:
            extra_tags.append("#ضربة_قاضية")

        base = base_hashtags.get(category, "#أخبار_القتال")
        extra = " ".join(list(set(extra_tags)))

        if extra:
            return f"{base} {extra}"

        return base


# ═══════════════════════════════════════════════════════════════
# 🤖 البوت الرئيسي
# ═══════════════════════════════════════════════════════════════

class CombatSportsNewsBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.fetcher = NewsFetcher(self.db)
        self.generator = ContentGenerator(self.db)
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.running = False

        logging.info("=" * 60)
        logging.info("🥊 بوت وكالة أخبار الرياضات القتالية - تم التشغيل")
        logging.info("=" * 60)

    async def start(self):
        self.running = True
        await self._verify_setup()

        tasks = [
            asyncio.create_task(self._fetching_loop()),
            asyncio.create_task(self._publishing_loop()),
            asyncio.create_task(self._maintenance_loop()),
        ]

        logging.info(
            f"✅ البوت يعمل! الجلب كل {FETCH_INTERVAL_MINUTES} دقيقة، "
            f"النشر كل {PUBLISH_INTERVAL_MINUTES} دقائق"
        )

        await asyncio.gather(*tasks)

    async def _verify_setup(self):
        try:
            me = await self.bot.get_me()
            logging.info(f"البوت متصل: @{me.username} (ID: {me.id})")

            try:
                chat = await self.bot.get_chat(TELEGRAM_CHANNEL_ID)
                logging.info(f"تم التحقق من القناة: {chat.title}")

            except Exception as e:
                logging.warning(f"تعذر التحقق من القناة: {e}")
                logging.warning("تأكد أن البوت مسؤول في القناة!")

        except Exception as e:
            logging.error(f"فشل التحقق من البوت: {e}")
            raise

    async def _fetching_loop(self):
        logging.info(
            f"📡 بدأت حلقة الجلب (كل {FETCH_INTERVAL_MINUTES} دقيقة)"
        )

        await self._fetch_news()

        while self.running:
            await asyncio.sleep(FETCH_INTERVAL_MINUTES * 60)

            if self.running:
                await self._fetch_news()

    async def _fetch_news(self):
        logging.info("🔍 بدء جولة جلب الأخبار...")

        try:
            news_items = self.fetcher.fetch_all_feeds()
            added_count = 0

            for item in news_items:
                if self.db.is_link_published(item["link"]):
                    continue

                success = self.db.add_to_queue(
                    link=item["link"],
                    title=item["title"],
                    summary=item["summary"],
                    category=item["category"],
                    image_url=item.get("image_url")
                )

                if success:
                    added_count += 1

            queue_size = self.db.get_queue_size()

            logging.info(
                f"✅ انتهت الجلب: {added_count} خبر جديد. "
                f"حجم الطابور: {queue_size}"
            )

        except Exception as e:
            logging.error(f"❌ خطأ في الجلب: {e}")
            self.db.log_error(str(e), "fetch_news")

    async def _publishing_loop(self):
        logging.info(
            f"📤 بدأت حلقة النشر (كل {PUBLISH_INTERVAL_MINUTES} دقائق)"
        )

        while self.running:
            await asyncio.sleep(PUBLISH_INTERVAL_MINUTES * 60)

            if self.running:
                await self._publish_next()

    async def _publish_next(self):
        try:
            today_count = self.db.get_today_posts_count()

            if today_count >= MAX_DAILY_POSTS:
                logging.info(
                    f"📊 تم الوصول للحد اليومي ({today_count}/{MAX_DAILY_POSTS})"
                )
                return

            item = self.db.get_next_from_queue()

            if not item:
                logging.info("📭 الطابور فارغ، لا يوجد ما ينشر")
                return

            logging.info(f"📝 معالجة: {item['title'][:60]}...")

            post_data = self.generator.generate_news_post(item)

            if not post_data:
                logging.error("فشل توليد المحتوى، تم تخطيه")
                self.db.mark_queue_item_processed(item["id"])
                return

            await self._send_to_channel(post_data)

            self.db.mark_queue_item_processed(item["id"])

            self.db.add_published_link(
                link=item["link"],
                title=item["title"],
                category=item["category"]
            )

            self.db.increment_today_posts()

            queue_size = self.db.get_queue_size()

            logging.info(
                f"✅ تم النشر بنجاح! المتبقي في الطابور: {queue_size}"
            )

        except Exception as e:
            logging.error(f"❌ خطأ في النشر: {e}")
            self.db.log_error(str(e), "publish_next")

    async def _send_to_channel(self, post_data: dict):
        message = MESSAGE_TEMPLATE.format(
            title=post_data["title"],
            content=post_data["content"],
            url=post_data["url"],
            hashtags=post_data["hashtags"]
        )

        if len(message) > 4096:
            message = message[:4090] + "..."

        image_url = post_data.get("image_url")

        try:
            if image_url:
                await self.bot.send_photo(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    photo=image_url,
                    caption=message,
                    parse_mode=ParseMode.HTML
                )
            else:
                await self.bot.send_message(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    text=message,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )

        except Exception as e:
            if image_url and "photo" in str(e).lower():
                logging.warning(
                    f"فشل إرسال الصورة، إرسال نص فقط: {e}"
                )

                await self.bot.send_message(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    text=message,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )
            else:
                raise

    async def _maintenance_loop(self):
        while self.running:
            await asyncio.sleep(24 * 60 * 60)

            if not self.running:
                break

            try:
                removed = self.db.clean_old_links(days=30)
                logging.info(
                    f"🧹 صيانة: تم حذف {removed} رابط قديم"
                )

                cleared = self.db.clear_processed_queue()
                logging.info(
                    f"🧹 صيانة: تم مسح {cleared} عنصر من الطابور"
                )

            except Exception as e:
                logging.error(f"❌ خطأ في الصيانة: {e}")

    async def stop(self):
        logging.info("🛑 إيقاف البوت...")
        self.running = False
        await self.bot.session.close()


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

    bot = CombatSportsNewsBot()

    try:
        await bot.start()

    except KeyboardInterrupt:
        logging.info("تم استقبال إشارة إيقاف")

    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
