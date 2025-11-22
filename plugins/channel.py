import re
import hashlib
import requests
from info import *
from utils import *
from pyrogram import Client, filters
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Advanced Language Mapping (Short Code -> Full Name)
LANG_MAP = {
    "hi": "Hindi", "hin": "Hindi",
    "en": "English", "eng": "English",
    "bn": "Bengali", "ban": "Bengali", "ben": "Bengali",
    "tm": "Tamil", "tam": "Tamil",
    "te": "Telugu", "tel": "Telugu",
    "ml": "Malayalam", "mal": "Malayalam",
    "kn": "Kannada", "kan": "Kannada",
    "mr": "Marathi", "pa": "Punjabi",
    "gu": "Gujarati", "ko": "Korean",
    "ja": "Japanese", "es": "Spanish",
    "fr": "French", "ur": "Urdu",
    "dual": "Dual Audio", "multi": "Multi Audio"
}

notified_movies = set()
user_reactions = {}
reaction_counts = {}

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
        # 1. Basic Cleaning for Searching
        search_name = re.sub(r'https?://\S+', '', file_name)
        search_name = re.sub(r'@\w+', '', search_name).replace('_', ' ').replace('.', ' ')
        
        # Extract Year for Search
        year_match = re.search(r"\b(19|20)\d{2}\b", caption) or re.search(r"\b(19|20)\d{2}\b", file_name)
        year = year_match.group(0) if year_match else None
        
        if year:
             search_query = search_name[:search_name.find(year) + 4]
        else:
             search_query = search_name

        # 2. Fetch Data from TMDB
        tmdb_data = await fetch_tmdb_data(search_query, year)
        
        title = tmdb_data.get("title", search_name)
        overview = tmdb_data.get("overview", "")
        rating = tmdb_data.get("vote_average", "N/A")
        genres = tmdb_data.get("genres", "Movie")
        poster = tmdb_data.get("poster")
        tmdb_year = tmdb_data.get("release_date", year or "N/A")[:4]

        # 3. Advanced Language Detection
        language = await get_formatted_language(caption)
        
        # 4. Quality Detection
        quality = await get_qualities(caption) or "HDRip"

        # 5. Clean Display Name (Strict Cleaning as per request)
        display_name = await clean_display_name(file_name)

        # 6. Unique ID for Reactions
        search_movie_slug = file_name.replace(" ", "-")
        unique_id = generate_unique_id(search_movie_slug)
        
        if unique_id not in reaction_counts:
            reaction_counts[unique_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[unique_id] = {}

        # 7. Constructing the Beautiful Caption
        
        # Header
        full_caption = "#𝑵𝒆𝒘_𝑪𝒐𝒏𝒕𝒆𝒏𝒕_𝑨𝒅𝒅𝒆𝒅 💌\n━━━━━━━━━━━━━━━━━\n"
        
        # File Section
        full_caption += f"📂 <b>File:</b> {display_name}\n━━━━━━━━━━━━━━━━━\n"
        
        # Storyline Section (Only if overview exists and is not too short)
        if overview and len(overview) > 10:
            # Truncate if too long (max 300 chars) to keep design clean
            short_overview = overview[:300] + "..." if len(overview) > 300 else overview
            full_caption += f"📝 <b>Storyline:</b>\n{short_overview}\n━━━━━━━━━━━━━━━━━\n"

        # Box Details Section
        full_caption += (
            "╭───────────────╮\n"
            f"│ 🎭 <b>Genre:</b> {genres}\n"
            f"│ 📅 <b>Year:</b> {tmdb_year}\n"
            f"│ 🔊 <b>Language:</b> {language}\n"
            f"│ 💿 <b>Quality:</b> {quality}\n"
            f"│ 🌟 <b>Rating:</b> {rating}/10\n"
            "╰───────────────╯\n\n"
        )

        # Footer
        full_caption += "𝐓𝐨 𝐚𝐜𝐜𝐞𝐬𝐬 𝐭𝐡𝐢𝐬 𝐜𝐨𝐧𝐭𝐞𝐧𝐭, 𝐩𝐥𝐞𝐚𝐬𝐞 𝐜𝐥𝐢𝐜𝐤 𝐭𝐡𝐞 𝐆𝐞𝐭 𝐅𝐢𝐥𝐞 💌 𝐛𝐮𝐭𝐭𝐨𝐧 𝐛𝐞𝐥𝐨𝐰\n━━━━━━━━━━━━━━━━━"

        # Buttons
        buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[unique_id]['❤️']}", callback_data=f"r_{unique_id}_{search_movie_slug}_heart"),
            InlineKeyboardButton(f"👍 {reaction_counts[unique_id]['👍']}", callback_data=f"r_{unique_id}_{search_movie_slug}_like"),
            InlineKeyboardButton(f"👎 {reaction_counts[unique_id]['👎']}", callback_data=f"r_{unique_id}_{search_movie_slug}_dislike"),
            InlineKeyboardButton(f"🔥 {reaction_counts[unique_id]['🔥']}", callback_data=f"r_{unique_id}_{search_movie_slug}_fire")
        ], [
            InlineKeyboardButton('💌 Get File 🍿', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_movie_slug}')
        ]]

        # Send Logic
        if poster:
            await bot.send_photo(
                chat_id=MOVIE_UPDATE_CHANNEL,
                photo=poster,
                caption=full_caption,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            await bot.send_message(
                chat_id=MOVIE_UPDATE_CHANNEL,
                text=full_caption,
                reply_markup=InlineKeyboardMarkup(buttons),
                disable_web_page_preview=True
            )

    except Exception as e:
        print(f"Error in send_movie_update: {e}")

@Client.on_callback_query(filters.regex(r"^r_"))
async def reaction_handler(client, query):
    try:
        data = query.data.split("_")
        if len(data) < 4: return        
        
        unique_id = data[1]
        search_movie = "_".join(data[2:-1]) 
        new_reaction = data[-1]
        user_id = query.from_user.id
        
        emoji_map = {"heart": "❤️", "like": "👍", "dislike": "👎", "fire": "🔥"}
        if new_reaction not in emoji_map: return
        new_emoji = emoji_map[new_reaction]       
        
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
            InlineKeyboardButton(f"❤️ {reaction_counts[unique_id]['❤️']}", callback_data=f"r_{unique_id}_{search_movie}_heart"),                
            InlineKeyboardButton(f"👍 {reaction_counts[unique_id]['👍']}", callback_data=f"r_{unique_id}_{search_movie}_like"),
            InlineKeyboardButton(f"👎 {reaction_counts[unique_id]['👎']}", callback_data=f"r_{unique_id}_{search_movie}_dislike"),
            InlineKeyboardButton(f"🔥 {reaction_counts[unique_id]['🔥']}", callback_data=f"r_{unique_id}_{search_movie}_fire")
        ],[
            InlineKeyboardButton('💌 Get File 🍿', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_movie}')
        ]]
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(updated_buttons))
    except Exception as e:
        print("Reaction error:", e)

# --- Helper Functions ---

async def clean_display_name(filename):
    """
    Cleans the filename to remove GB, MB, Quality tags, brackets, etc.
    Example: "Pushpa.The.Rise.2021.1080p.WEB-DL.2.1GB.mkv" -> "Pushpa The Rise 2021"
    """
    # 1. Remove Extension
    name = re.sub(r'\.\w+$', '', filename)
    
    # 2. Remove Website links or @mentions
    name = re.sub(r'https?://\S+|@\w+', '', name)

    # 3. Remove Quality Tags, Sizes, Codecs (Case Insensitive)
    # This list covers common unwanted terms
    unwanted = r'\b(?:1080p|720p|480p|2160p|4k|5k|HEVC|WEB-DL|BluRay|HDRip|HDTC|HDTS|CAMRip|HDCAM|DVDRip|DVDScr|WEBRip|x264|x265|10bit|60fps|AAC|5\.1|Dual|Audio|Multi|Sub|ESub|Line|GB|MB|KB)\b'
    name = re.sub(unwanted, '', name, flags=re.IGNORECASE)

    # 4. Remove File Size numbers like "2.1" if followed by nothing (leftover from 2.1GB)
    name = re.sub(r'\b\d+(\.\d+)?\b(?=\s*$)', '', name)

    # 5. Remove Brackets (), [], {}
    name = re.sub(r'[\[\(\{\]\)\}]', '', name)

    # 6. Replace dots, underscores, dashes with space
    name = re.sub(r'[._-]', ' ', name)

    # 7. Remove extra spaces
    return re.sub(r'\s{2,}', ' ', name).strip()

async def get_formatted_language(text):
    """
    Detects languages from text (short codes or full names) and returns a formatted string.
    Example: "Hi, En, Tam" -> "Hindi, English, Tamil"
    """
    found_langs = set()
    text_lower = text.lower()
    
    # Check for exact keys in mapping
    for code, full_name in LANG_MAP.items():
        # Use regex to match whole words to avoid partial matches (e.g. 'hi' inside 'high')
        if re.search(r'\b' + re.escape(code) + r'\b', text_lower):
            found_langs.add(full_name)
            
    # If no known short codes found, try to keep original if it looks like a language
    # But usually, the map covers most. If empty, default to Unknown.
    if not found_langs:
        return "Unknown"
        
    return ", ".join(sorted(found_langs))

async def get_qualities(text):
    quality_list = ["ORG", "HDCAM", "CAMRip", "WEB-DL", "HDRip", "HDTC", "HDTS", "HQ", "DVDscr", "DVDRip", "BluRay", "4K", "1080p"]
    text_lower = text.lower()
    for quality in quality_list:
        if quality.lower() in text_lower:
            return quality
    return None

async def fetch_tmdb_data(query, year=None):
    try:
        params = {"api_key": TMDB_API, "query": query}
        if year:
            params["year"] = year
            
        res = requests.get("https://api.themoviedb.org/3/search/movie", params=params, timeout=5)
        results = res.json().get("results", [])
        
        if not results:
            return {}
            
        # Get the best match
        movie = results[0]
        movie_id = movie.get("id")
        
        # Fetch detailed info (specifically for Genres)
        details_res = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API}", timeout=5)
        details = details_res.json()
        
        poster_path = details.get("poster_path") or movie.get("poster_path")
        backdrop_path = details.get("backdrop_path")
        
        image_url = None
        if poster_path:
            image_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        elif backdrop_path:
            image_url = f"https://image.tmdb.org/t/p/w500{backdrop_path}"

        # Extract Genres
        genres_list = [g["name"] for g in details.get("genres", [])]
        genres_str = ", ".join(genres_list[:2]) # Take top 2 genres
        
        return {
            "title": details.get("title"),
            "overview": details.get("overview"),
            "vote_average": round(details.get("vote_average", 0), 1),
            "genres": genres_str,
            "release_date": details.get("release_date"),
            "poster": image_url
        }
    except Exception as e:
        print(f"TMDB Error: {e}")
        return {}

def generate_unique_id(movie_name):
    return hashlib.md5(movie_name.encode('utf-8')).hexdigest()[:5]
