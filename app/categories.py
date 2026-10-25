"""App classification shared by the TaskDash server and the TrueDuty app.
Every activity minute gets a category (what kind of work) and a class: work, off (not work) or new (not rated yet).
Admins override both with rules: an app name, a word in the window title, or both. A title rule wins over an app rule."""
import re

CATEGORIES = ['Development', 'Design', 'Communication', 'Meetings', 'Project management', 'Documents', 'File sharing', 'Browsing', 'Entertainment', 'Other']
CAT_CLASS = {'Development': 'work', 'Design': 'work', 'Communication': 'work', 'Meetings': 'work', 'Project management': 'work', 'Documents': 'work',
             'File sharing': 'work', 'Browsing': 'work', 'Entertainment': 'off', 'Other': 'new'}

# app name fragments (lower case, letters and digits only) -> category
_APPS = [
    ('Browsing', 'chrome chromium msedge edge firefox brave opera vivaldi safari arc zen librewolf waterfox tor yandex'),
    ('Development', 'code cursor windsurf pycharm idea intellij webstorm phpstorm clion goland rider datagrip rubymine androidstudio studio64 devenv visualstudio '
                    'sublime notepadplusplus notepad++ vim nvim neovim emacs xcode terminal windowsterminal wt cmd powershell pwsh conhost iterm alacritty wezterm kitty konsole '
                    'gnometerminal xterm gitbash mintty githubdesktop sourcetree gitkraken postman insomnia docker dbeaver mysqlworkbench heidisql tableplus pgadmin '
                    'python node java wsl putty claude chatgpt copilot jupyter anaconda zed fleet'),
    ('Design', 'figma photoshop illustrator indesign xd aftereffects afterfx premiere blender gimp inkscape krita affinity sketch canva resolve davinci lightroom coreldraw'),
    ('Meetings', 'zoom webex gotomeeting'),
    ('Communication', 'slack teams msteams discord telegram whatsapp skype signal outlook olk thunderbird mail element viber zulip mattermost'),
    ('Project management', 'jira trello asana clickup linear todoist taskdash monday basecamp youtrack'),
    ('Documents', 'winword word excel powerpnt powerpoint onenote acrobat acrord32 foxit libreoffice soffice wps notepad obsidian typora evernote notion pages numbers keynote'),
    ('File sharing', 'explorer finder nautilus dolphin thunar nemo dropbox onedrive googledrivefs filezilla winscp 7zfm winrar cyberduck'),
    ('Entertainment', 'steam steamwebhelper epicgameslauncher spotify vlc netflix battlenet riotclient leagueoflegends valorant minecraft robloxplayerbeta roblox dota2 cs2 csgo '
                      'eadesktop origin galaxyclient twitch music mpchc potplayer itunes primevideo hearthstone fortnite'),
]
APP_CAT = {}
for cat, names in _APPS:
    for n in names.split(): APP_CAT[n] = cat
BROWSERS = {n for n in _APPS[0][1].split()}

# words in a browser tab title -> category (browser pages are never listed one by one, they only shape the category)
_TITLE = [
    ('Meetings', 'meet.google|google meet|zoom meeting|teams meeting|jitsi|whereby'),
    ('Communication', 'gmail|inbox|outlook|slack|whatsapp|telegram|discord|messenger'),
    ('Project management', 'jira|trello|asana|clickup|linear|notion|monday.com|basecamp|taskdash'),
    ('Development', 'github|gitlab|bitbucket|stack overflow|stackoverflow|localhost|127.0.0.1|mdn web docs|npm|pypi|vercel|netlify|cloudflare|aws console|docker hub|codepen'),
    ('Documents', 'google docs|google sheets|google slides|docs.google|office.com|confluence'),
    ('Design', 'figma|canva|miro|dribbble|behance|whimsical'),
    ('File sharing', 'google drive|dropbox|onedrive|wetransfer|mega.nz|box.com'),
    ('Entertainment', 'youtube|netflix|twitch|facebook|instagram|tiktok|reddit|spotify|prime video|9gag|hotstar'),
]
_TITLE_RX = [(c, re.compile(r'(?<![a-z0-9])(' + '|'.join(re.escape(w) for w in ws.split('|')) + r')(?![a-z0-9])')) for c, ws in _TITLE]
ITEM_CATS = {'Development', 'Design', 'Documents', 'Entertainment'}     # only these list files and games one by one

def clean_app(a):
    a = (a or '').strip(); a = re.sub(r'\.(exe|app|bin)$', '', a, flags=re.I); return a[:60]
def key_of(a): return re.sub(r'[^a-z0-9+]', '', clean_app(a).lower())
def default_cat(app, title=''):
    k = key_of(app)
    if not k: return 'Other'
    cat = APP_CAT.get(k)
    if not cat:
        for name, c in APP_CAT.items():
            if len(name) >= 4 and (k.startswith(name) or (len(name) >= 5 and k.endswith(name))): cat = c; break
    if cat == 'Browsing' and title:
        t = title.lower()
        for c, rx in _TITLE_RX:
            if rx.search(t): return c
    return cat or 'Other'
def is_browser(app):
    k = key_of(app); return k in BROWSERS or any(k.startswith(b) for b in BROWSERS if len(b) >= 5)

SUFFIXES = ('Google Chrome', 'Mozilla Firefox', 'Microsoft Edge', 'Brave', 'Opera', 'Vivaldi', 'Visual Studio Code', 'Cursor', 'Safari', 'Chromium', 'Sublime Text',
            'Notepad++', 'Notepad', 'Word', 'Excel', 'PowerPoint', 'Figma', 'Adobe Photoshop', 'GIMP', 'Inkscape', 'Blender', 'IntelliJ IDEA', 'PyCharm', 'WebStorm')
def item_of(app, title, cat):
    """A file, document or game name worth listing, or '' (browser pages are never listed)."""
    if cat not in ITEM_CATS or is_browser(app): return ''
    t = re.sub(r'\s+', ' ', (title or '')).strip()
    for s in SUFFIXES:
        if t.endswith(' - ' + s): t = t[:-(len(s) + 3)]; break
    t = re.sub(r'^[●•*]\s*', '', t)                                # unsaved marker
    t = re.sub(r'\s*\(\d+\s*[x×]\s*\d+\)\s*$', '', t)              # image size suffix
    t = re.sub(r'\s+-\s+[^-]{0,40}$', '', t) if cat == 'Development' and ' - ' in t else t   # "file.py - project" -> "file.py"
    if len(t) < 2 or re.fullmatch(r'[\d\s.%()×x-]+', t): return ''
    return t[:120]

def classify(rules, app, title):
    """-> (cls, category). rules: list of dicts with app, pattern, cls, category."""
    a = key_of(app); t = (title or '').lower(); best_cls = best_cat = None; sc_cls = sc_cat = -1
    for r in rules:
        ra = key_of(r.get('app')); rp = (r.get('pattern') or '').lower()
        if ra and ra != a: continue
        if rp and rp not in t: continue
        sc = (2 if rp else 0) + (1 if ra else 0)
        if r.get('cls') and sc > sc_cls: best_cls, sc_cls = r['cls'], sc
        if r.get('category') and sc > sc_cat: best_cat, sc_cat = r['category'], sc
    cat = best_cat or default_cat(app, title)
    return best_cls or CAT_CLASS.get(cat, 'new'), cat

NAMES = {'code': 'VS Code', 'chrome': 'Chrome', 'msedge': 'Edge', 'firefox': 'Firefox', 'winword': 'Word', 'excel': 'Excel', 'powerpnt': 'PowerPoint', 'onenote': 'OneNote',
         'explorer': 'File Explorer', 'windowsterminal': 'Terminal', 'wt': 'Terminal', 'cmd': 'Command Prompt', 'pwsh': 'PowerShell', 'powershell': 'PowerShell',
         'olk': 'Outlook', 'outlook': 'Outlook', 'msteams': 'Teams', 'teams': 'Teams', 'zoom': 'Zoom', 'slack': 'Slack', 'figma': 'Figma', 'steam': 'Steam',
         'devenv': 'Visual Studio', 'studio64': 'Android Studio', 'acrord32': 'Acrobat Reader', 'soffice': 'LibreOffice', 'notepad': 'Notepad', 'notepad++': 'Notepad++',
         'spotify': 'Spotify', 'discord': 'Discord', 'telegram': 'Telegram', 'whatsapp': 'WhatsApp', 'brave': 'Brave', 'opera': 'Opera', 'vivaldi': 'Vivaldi', 'claude': 'Claude'}
def label_of(app):
    k = key_of(app); return NAMES.get(k) or (clean_app(app)[:1].upper() + clean_app(app)[1:])
