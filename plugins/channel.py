import re
import hashlib
import requests
from datetime import datetime, timedelta
from info import *
from utils import *
from pyrogram import Client, filters
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# 1. UPDATED FULL LANGUAGE MAP
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

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    """Media Handler"""
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

async def send_movie_update(bot, file_name, caption):
    try:
        # --- 1. Smart Link & 5-Day Check ---
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

        # --- 2. Smart Search Query ---
        clean_name = re.sub(r'\.\w+$', '', file_name)
        clean_name = re.sub(r'https?://\S+|@\w+', '', clean_name)
        year_match = re.search(r"\b(19|20)\d{2}\b", clean_name)
        year = year_match.group(0) if year_match else None
        
        if year:
             search_query = clean_name[:clean_name.find(year)]
        else:
             search_query = clean_name

        search_query = await clean_search_query(search_query)

        # --- 3. Fetch Data ---
        tmdb_data = await fetch_tmdb_data(search_query, year)
        
        display_name = await clean_display_name(file_name)
        
        title = tmdb_data.get("title", display_name)
        overview = tmdb_data.get("overview", "")
        rating = tmdb_data.get("vote_average", 0)
        genres = tmdb_data.get("genres", "")
        poster = tmdb_data.get("poster")
        tmdb_year = tmdb_data.get("release_date", year or "N/A")[:4]
        
        language = await get_formatted_language(file_name, caption)
        quality = await get_qualities(caption)

        if unique_id not in reaction_counts:
            reaction_counts[unique_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[unique_id] = {}

        # --- 4. DESIGN SECTION (DESIGN 1: CINEMATIC BOX) ---
        
        # Header
        full_caption = f"⚡️ <b>{title} ({tmdb_year})</b>\n\n"
        
        # Start Box
        full_caption += "╭─❮ <b>ᴍᴏᴠɪᴇ ɪɴꜰᴏ</b> ❯───\n"
        
        # Box Content (Conditional)
        if genres: 
            full_caption += f"│ 🎭 <b>Genre:</b> {genres}\n"
        if rating and str(rating) != "0" and str(rating) != "0.0":
            full_caption += f"│ ⭐️ <b>Rating:</b> {rating}/10\n"
        if quality:
            full_caption += f"│ 💿 <b>Quality:</b> {quality}\n"
        if language != "Unknown":
            full_caption += f"│ 🔊 <b>Language:</b> {language}\n"
            
        # End Box
        full_caption += "╰───────────────\n\n"
        
        # Storyline (Conditional)
        if poster and overview and len(overview) > 10:
            short_overview = overview[:250] + "..." if len(overview) > 250 else overview
            full_caption += f"📝 <b>Storyline:</b>\n{short_overview}\n\n"
        
        # File Name
        full_caption += f"📂 <b>File:</b> <code>{display_name}</code>\n"
        
        # Footer
        full_caption += "━━━━━━━━━━━━━━━━━\n"
        full_caption += "👇 <b>Get This File Below</b> 👇"

        # --- 5. Buttons ---
        buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[unique_id]['❤️']}", callback_data=f"r_{unique_id}_h"),
            InlineKeyboardButton(f"👍 {reaction_counts[unique_id]['👍']}", callback_data=f"r_{unique_id}_l"),
            InlineKeyboardButton(f"👎 {reaction_counts[unique_id]['👎']}", callback_data=f"r_{unique_id}_d"),
            InlineKeyboardButton(f"🔥 {reaction_counts[unique_id]['🔥']}", callback_data=f"r_{unique_id}_f")
        ], [
            InlineKeyboardButton('📂 Get File 📂', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{link_slug}')
        ]]

        if poster:
            await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=poster, caption=full_caption, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await bot.send_message(chat_id=MOVIE_UPDATE_CHANNEL, text=full_caption, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

    except Exception as e:
        print(f"Error in send_movie_update: {e}")

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
        ],[
            InlineKeyboardButton('📂 Get File 📂', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{link_slug}')
        ]]
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(updated_buttons))
    except Exception as e:
        print("Reaction error:", e)

# --- Helper Functions ---

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

async def clean_display_name(filename):
    name = re.sub(r'\.\w+$', '', filename)
    name = re.sub(r'https?://\S+|@\w+', '', name)
    unwanted = r'\b(?:1080p|720p|480p|2160p|4k|5k|HEVC|WEB-DL|BluRay|HDRip|HDTC|HDTS|CAMRip|HDCAM|DVDRip|DVDScr|WEBRip|x264|x265|10bit|60fps|AAC|AAC5\.1|5\.1|Dual|Audio|Multi|Sub|ESub|Line|GB|MB|KB|Downlo|Download|Netflix|Amazon|NF|AV1|ViSTA|V2|PROPER)\b'
    name = re.sub(unwanted, '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b\d+(\.\d+)?\b(?=\s*$)', '', name)
    name = re.sub(r'[\[\(\{\]\)\}]', '', name)
    name = re.sub(r'[._-]', ' ', name)
    return re.sub(r'\s{2,}', ' ', name).strip()

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
    quality_list = ["ORG", "HDCAM", "CAMRip", "WEB-DL", "HDRip", "HDTC", "HDTS", "HQ", "DVDscr", "DVDRip", "BluRay", "WEBRip", "PreDVDRip"]
    text_lower = text.lower()
    for quality in quality_list:
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
        if not matched_movie: return {} 
        
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
    return hashlib.md5(movie_name.encode('utf-8')).hexdigest()[:5]
    
