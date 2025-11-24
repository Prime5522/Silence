import re
import hashlib
import requests
import textwrap
from datetime import datetime, timedelta
from info import *
from utils import *
from pyrogram import Client, filters
from database.ia_filterdb import save_file
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# 1. FULL LANGUAGE MAP
LANG_MAP = {
    "hi": "Hindi", "hin": "Hindi", "hindi": "Hindi",
    "en": "English", "eng": "English", "english": "English",
    "bn": "Bengali", "ban": "Bengali", "ben": "Bengali", "bengali": "Bengali",
    "tm": "Tamil", "tam": "Tamil", "tamil": "Tamil",
    "te": "Telugu", "tel": "Telugu", "telugu": "Telugu",
    "ml": "Malayalam", "mal": "Malayalam", "malayalam": "Malayalam",
    "kn": "Kannada", "kan": "Kannada", "kannada": "Kannada",
    "mr": "Marathi", "marathi": "Marathi",
    "pa": "Punjabi", "punjabi": "Punjabi",
    "gu": "Gujarati", "gujarati": "Gujarati",
    "ko": "Korean", "korean": "Korean",
    "ja": "Japanese", "japanese": "Japanese",
    "es": "Spanish", "spanish": "Spanish",
    "fr": "French", "french": "French",
    "ur": "Urdu", "urdu": "Urdu",
    "dual": "Dual Audio", "multi": "Multi Audio"
}

# Global Storage
notified_movies = {}
user_reactions = {}
reaction_counts = {}
movie_slugs = {}

media_filter = filters.document | filters.video | filters.audio

# ---------- Helper: Quality List ----------
QUALITY_LIST = [
    "UNCUT", "UN CUT", "DIRECTOR'S CUT", "DIRCUT", "DCUT",
    "REMASTERED", "REMASTER", "ORG", "ORIGINAL",
    "HDCAM", "HD CAM", "CAMRIP", "CAM RIP", "CAM",
    "HDTC", "HD TC", "HDTS", "HD TS", "TS", "TELESYNC",
    "TC", "TELECINE", "WEB-DL", "WEBDL", "WEB DL", "WEB",
    "WEB-RIP", "WEBRIP", "WEB RIP", "HDRIP", "HD RIP",
    "DVDRIP", "DVD RIP", "DVDSCR", "DVD SCR", "DVDSCREEN",
    "PRE DVDRIP", "PREDVDRIP", "PRE DVD RIP",
    "BLURAY", "BLU RAY", "BRRIP", "BDRIP",
    "SCR", "SCREENER", "HC", "HARDSUB", "HC HDRIP",
    "HQ", "HIGH QUALITY", "RIP", "RIPPED",
    "4K", "UHD", "FHD", "60FPS", "50FPS",
    "NF", "NETFLIX", "AMZN", "AMAZON", "DSNP", "DISNEY",
    "HMAX", "HBOMAX", "HBO", "APLTV", "APPLE TV", "HULU",
    "LINE AUDiO", "MIC", "MIC DUB", "HQ WEBDL", "HQ WEB-DL", "HD",
    "DL", "WEB", "CAM", "RIP", "SCR", "BR"
]

# ---------- Helper: Build Boxed Text ----------
def build_box(title, lines, wrap_width=40, padding=2):
    wrapped = []
    for line in lines:
        wrapped_lines = textwrap.wrap(line, width=wrap_width) or [""]
        wrapped.extend(wrapped_lines)

    max_line_len = max([len(l) for l in wrapped] + [len(title)]) 
    inner_width = min(max_line_len, wrap_width)
    inner_width = max(inner_width, len(title))
    total_inner = inner_width + padding * 2

    title_center = title.center(total_inner)
    top = "╭" + "─" * (total_inner + 2) + "╮\n"
    if title:
        title_row = "│ " + title_center + " │\n"
        divider = "├" + "─" * (total_inner + 2) + "┤\n"
        header = top + title_row + divider
    else:
        # If no title (like get file box), just top border
        header = top

    content = ""
    for l in wrapped:
        padded = l.ljust(total_inner)
        content += "│ " + padded + " │\n"

    bottom = "╰" + "─" * (total_inner + 2) + "╯\n"
    return header + content + bottom

# ---------- Helper: Smart Title Logic ----------
YEAR_RE = re.compile(r'^(19|20)\d{2}$')

async def smart_title_from_filename(filename, tmdb_data=None):
    if tmdb_data and tmdb_data.get("title"):
        return tmdb_data.get("title")

    name = re.sub(r'\.\w+$', '', filename)
    name = re.sub(r'https?://\S+|@\w+', '', name)
    name = re.sub(r'[_\.\-]+', ' ', name)
    name = re.sub(r'\s{2,}', ' ', name).strip()
    if not name:
        return filename[:40]

    words = name.split()
    first5 = words[:5]
    for idx, w in enumerate(first5):
        if YEAR_RE.match(w):
            selected = words[: idx + 1 ]
            res = " ".join(selected)
            return res

    selected = words[:4]
    title = " ".join(selected)
    if len(words) > 4:
        title = title + "…"
    return title

# ---------- Other Helpers ----------
async def get_smart_link_slug(filename):
    clean = re.sub(r'\.\w+$', '', filename)
    clean = re.sub(r'https?://\S+|@\w+', '', clean)
    clean_text = re.sub(r'[^a-zA-Z0-9\s]', ' ', clean)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    words = clean_text.split()
    selected_words = []
    found_year = False
    for i in range(min(len(words), 3)):
        word = words[i]
        if re.match(r'^(19|20)\d{2}$', word):
            selected_words = words[:i+1]
            found_year = True
            break
    if not found_year:
        selected_words = words[:3]
    base_slug = "-".join(selected_words)
    final_slug = re.sub(r'[^a-zA-Z0-9\-]', '', base_slug)
    return final_slug

async def clean_search_query(text):
    text = re.sub(r'[._\-\(\)\[\]\{\}]', ' ', text)
    text = re.sub(r'\b(S\d+|Season\s*\d+|Ep?\d+)\b', '', text, flags=re.IGNORECASE)
    junk = r'\b(Download|Downlo|Complete|Netflix|Amazon|Prime|Hulu|Hotstar|Series|Movie|Official|Dubbed|Dual|Audio|Sub|ESub|NF|AV1|Vista|AAC|AAC5\.1)\b'
    text = re.sub(junk, '', text, flags=re.IGNORECASE)
    return re.sub(r'\s{2,}', ' ', text).strip()

async def get_formatted_language(filename, caption):
    text = (filename + " " + (caption or "")).lower()
    text = re.sub(r'[._\-\[\]\(\)]', ' ', text)
    found_langs = set()
    for code, full_name in LANG_MAP.items():
        if re.search(r'\b' + re.escape(code) + r'\b', text):
            found_langs.add(full_name)
    if not found_langs: return "Unknown"
    return ", ".join(sorted(found_langs))

async def get_qualities(text):
    text_lower = (text or "").lower()
    for quality in QUALITY_LIST:
        if quality.lower() in text_lower:
            return quality
    return None

async def fetch_tmdb_data(query, year=None):
    try:
        params = {"api_key": TMDB_API, "query": query}
        if year: params["year"] = year
        res = requests.get("https://api.themoviedb.org/3/search/movie", params=params, timeout=5)
        results = res.json().get("results", [])
        if not results: return {}

        matched_movie = None
        for movie in results:
            title = movie.get("title", "")
            if re.search(r'\b' + re.escape(query) + r'\b', title, re.IGNORECASE):
                matched_movie = movie
                break
        if not matched_movie:
            matched_movie = results[0]

        movie_id = matched_movie.get("id")
        details_res = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API}", timeout=5)
        details = details_res.json()

        poster_path = details.get("poster_path") or matched_movie.get("poster_path")
        backdrop_path = details.get("backdrop_path")
        image_url = None
        if poster_path: image_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        elif backdrop_path: image_url = f"https://image.tmdb.org/t/p/w500{backdrop_path}"

        genres_list = [g["name"] for g in details.get("genres", [])]
        genres_str = ", ".join(genres_list[:2])

        return {
            "title": details.get("title"),
            "overview": details.get("overview"),
            "vote_average": round(details.get("vote_average", 0), 1),
            "genres": genres_str,
            "release_date": details.get("release_date"),
            "poster": image_url
        }
    except Exception:
        return {}

def generate_unique_id(movie_name):
    return hashlib.md5(movie_name.encode('utf-8')).hexdigest()[:8]

# ---------- Handlers ----------
@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    for file_type in ("document", "video", "audio"):
        media = getattr(message, file_type, None)
        if media is not None:
            break
    else:
        return
    media.file_type = file_type
    media.caption = message.caption
    success, silentxbotz = await save_file(bot, media)
    try:
        if success and silentxbotz == 1 and await get_status(bot.me.id):
            await send_movie_update(bot, file_name=media.file_name, caption=media.caption)
    except Exception as e:
        print(f"Error In Movie Update - {e}")
        pass

@Client.on_callback_query(filters.regex(r"^r_"))
async def reaction_handler(client, query):
    try:
        data = query.data.split("_")
        if len(data) != 3: return

        unique_id = data[1]
        short_code = data[2]
        user_id = query.from_user.id

        code_map = {"h": "❤️", "l": "👍", "d": "👎", "f": "🔥"}
        if short_code not in code_map: return
        new_emoji = code_map[short_code]

        link_slug = movie_slugs.get(unique_id)
        if not link_slug:
            await query.answer("Bot restarted, link expired.", show_alert=True)
            return

        if unique_id not in reaction_counts:
            reaction_counts[unique_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[unique_id] = {}

        if user_id in user_reactions[unique_id]:
            old_emoji = user_reactions[unique_id][user_id]
            if old_emoji == new_emoji:
                await query.answer("You already reacted!", show_alert=False)
                return
            else:
                reaction_counts[unique_id][old_emoji] -= 1

        user_reactions[unique_id][user_id] = new_emoji
        reaction_counts[unique_id][new_emoji] += 1

        updated_buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[unique_id]['❤️']}", callback_data=f"r_{unique_id}_h"),
            InlineKeyboardButton(f"👍 {reaction_counts[unique_id]['👍']}", callback_data=f"r_{unique_id}_l"),
            InlineKeyboardButton(f"👎 {reaction_counts[unique_id]['👎']}", callback_data=f"r_{unique_id}_d"),
            InlineKeyboardButton(f"🔥 {reaction_counts[unique_id]['🔥']}", callback_data=f"r_{unique_id}_f")
        ], [
            InlineKeyboardButton('📂 Get File 📂', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{link_slug}')
        ]]
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(updated_buttons))
    except Exception as e:
        print("Reaction error:", e)

# ---------- FIXED send_movie_update Function ----------
async def send_movie_update(bot, file_name, caption):
    try:
        link_slug = await get_smart_link_slug(file_name)
        unique_id = generate_unique_id(link_slug)

        current_time = datetime.now()
        if unique_id in notified_movies:
            last_posted_time = notified_movies[unique_id]
            if (current_time - last_posted_time) < timedelta(days=5):
                print(f"Skipping update for {link_slug}: Posted recently.")
                return

        notified_movies[unique_id] = current_time
        movie_slugs[unique_id] = link_slug

        # Smart Search Query
        clean_name = re.sub(r'\.\w+$', '', file_name)
        clean_name = re.sub(r'https?://\S+|@\w+', '', clean_name)
        year_match = re.search(r"\b(19|20)\d{2}\b", clean_name)
        year = year_match.group(0) if year_match else None

        if year:
            search_query = clean_name[:clean_name.find(year)]
        else:
            search_query = clean_name

        search_query = await clean_search_query(search_query)

        # Fetch Data
        tmdb_data = await fetch_tmdb_data(search_query, year)
        title = await smart_title_from_filename(file_name, tmdb_data)

        overview = tmdb_data.get("overview", "")
        rating = tmdb_data.get("vote_average", 0)
        genres = tmdb_data.get("genres", "")
        poster = tmdb_data.get("poster")
        tmdb_year = tmdb_data.get("release_date", year or "N/A")[:4]

        language = await get_formatted_language(file_name, caption)
        quality = await get_qualities(caption)

        if not quality: quality = "Unknown"
        if language == "Unknown": language = "Not Sure"

        if unique_id not in reaction_counts:
            reaction_counts[unique_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[unique_id] = {}

        # 1. Build Essential Boxes First
        content_lines = []
        content_lines.append(f"📂 Title: {title}")
        if genres:
            content_lines.append(f"🎭 Genre: {genres}")
        if rating and str(rating) not in ["0", "0.0"]:
            content_lines.append(f"⭐ Rating: {rating}/10")
        content_lines.append(f"💎 Quality: {quality}")
        content_lines.append(f"🔊 Audio: {language}")
        if tmdb_year and tmdb_year != "N/A":
            content_lines.append(f"📅 Year: {tmdb_year}")

        content_box = build_box("CONTENT INFO", content_lines, wrap_width=36, padding=2)

        engage_lines = ["♡ Like   ◌ Comment   ⎙ Save   ➤ Share"]
        engage_box = build_box("ENGAGE WITH POST", engage_lines, wrap_width=36, padding=2)

        getfile_text = "⬇️ Get File Below ⬇️"
        getfile_box = build_box("", [getfile_text], wrap_width=36, padding=2)

        top_header = "#𝑵𝒆𝒘_𝑪𝒐𝒏𝒕𝒆𝒏𝒕_𝑨𝒅𝒅𝒆𝒅 💌\n\n"

        # Calculate space for story
        # Telegram limit 1024. Reserve 100 for safety.
        base_caption = top_header + content_box + "\n" + engage_box + "\n" + getfile_box
        remaining_len = 1024 - len(base_caption) - 100

        # 2. Build Story Box (Conditional)
        story_box = ""
        if overview and len(overview.strip()) > 10 and remaining_len > 50:
            overview = re.sub(r'\s+', ' ', overview).strip()
            
            # Truncate text to fit
            max_text_len = remaining_len - 100 
            if max_text_len < 50: max_text_len = 50
            
            if len(overview) > max_text_len:
                overview = overview[:max_text_len] + "..."
            
            story_lines = textwrap.wrap(overview, width=36)
            story_box_candidate = build_box("STORY BOX", story_lines, wrap_width=36, padding=2)
            
            # Check length again
            if len(base_caption) + len(story_box_candidate) + 5 < 1024:
                story_box = story_box_candidate + "\n"

        # 3. Final Assemble
        caption_text = top_header + content_box + "\n"
        if story_box:
            caption_text += story_box
        caption_text += engage_box + "\n"
        caption_text += getfile_box

        buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[unique_id]['❤️']}", callback_data=f"r_{unique_id}_h"),
            InlineKeyboardButton(f"👍 {reaction_counts[unique_id]['👍']}", callback_data=f"r_{unique_id}_l"),
            InlineKeyboardButton(f"👎 {reaction_counts[unique_id]['👎']}", callback_data=f"r_{unique_id}_d"),
            InlineKeyboardButton(f"🔥 {reaction_counts[unique_id]['🔥']}", callback_data=f"r_{unique_id}_f")
        ], [
            InlineKeyboardButton('📂 Get File 📂', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{link_slug}')
        ]]

        if poster:
            # Failsafe for photo caption length
            if len(caption_text) > 1024:
                caption_text = caption_text.replace(story_box, "")
            
            await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=poster, caption=caption_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(chat_id=MOVIE_UPDATE_CHANNEL, text=caption_text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True, parse_mode=ParseMode.HTML)

    except Exception as e:
        print(f"Error in send_movie_update: {e}")

