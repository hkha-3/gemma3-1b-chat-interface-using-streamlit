import streamlit as st
import json, os, random, string, requests
from datetime import datetime, timedelta

# --- CONFIGURATION ---
USER_FILE = "users.json"
LOG_FILE = "logs.json"
CODES_FILE = "codes.json"
OLLAMA_URL = "http://localhost:11434/api/generate"

# --- DATA PERSISTENCE ---
def load_data(file, default):
    if not os.path.exists(file): return default
    try:
        with open(file, "r") as f: return json.load(f)
    except: return default

def save_data(file, data):
    with open(file, "w") as f: json.dump(data, f, indent=4)

# --- LOGIC: CLEANUP & CODES ---
def validate_and_use_code(input_code):
    codes = load_data(CODES_FILE, {})
    if input_code in codes:
        c = codes[input_code]
        expiry = datetime.strptime(c['expiry'], "%Y-%m-%d %H:%M:%S")
        if not c.get('used', False) and datetime.now() < expiry:
            codes[input_code]['used'] = True
            save_data(CODES_FILE, codes)
            return True
    return False

# --- AUTHENTICATION LOGIC ---
if "auth" not in st.session_state:
    st.session_state.auth = {"status": False, "user": None, "is_admin": False}

db = load_data(USER_FILE, {"usernames": {}})

# --- LOGIN/SIGNUP UI ---
if not st.session_state.auth["status"]:
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")
        if st.button("Login"):
            if u in db["usernames"]:
                user_data = db["usernames"][u]
                if user_data.get("banned", False):
                    st.error("🚫 This account is temporarily banned.")
                elif user_data["password"] == p:
                    st.session_state.auth = {
                        "status": True, 
                        "user": u, 
                        "is_admin": user_data.get("is_admin", False)
                    }
                    st.rerun()
                else:
                    st.error("Invalid credentials")
            else:
                st.error("User not found")

    with tab2:
        is_first = len(db["usernames"]) == 0
        new_u = st.text_input("New Username")
        new_p = st.text_input("New Password", type="password")
        
        if is_first:
            st.info("First user detected: You will be the Admin.")
            s_code = None
        else:
            s_code = st.text_input("Signup Code")

        if st.button("Create Account"):
            if new_u in db["usernames"]:
                st.error("Username already taken.")
            elif is_first or validate_and_use_code(s_code):
                db["usernames"][new_u] = {
                    "password": new_p, 
                    "is_admin": is_first,
                    "banned": False
                }
                save_data(USER_FILE, db)
                st.success("Account created! Please log in.")
            else:
                st.error("Invalid or expired signup code.")

# --- MAIN APP ---
else:
    username = st.session_state.auth["user"]
    st.sidebar.title(f"Welcome, {username}")

    # --- ADMIN DASHBOARD ---
    if st.session_state.auth["is_admin"]:
        with st.sidebar.expander("🛠️ Admin Controls"):
            # 1. Generate Signup Codes
            st.write("---")
            st.subheader("Invite Users")
            hrs = st.number_input("Expiry (hours)", 1, 168, 24)
            if st.button("Generate Code"):
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                exp = (datetime.now() + timedelta(hours=hrs)).strftime("%Y-%m-%d %H:%M:%S")
                codes = load_data(CODES_FILE, {})
                codes[code] = {"expiry": exp, "used": False}
                save_data(CODES_FILE, codes)
                st.code(code)

            # 2. User Management
            st.write("---")
            st.subheader("Manage Users")
            current_db = load_data(USER_FILE, {"usernames": {}})
            for u_name, u_info in list(current_db["usernames"].items()):
                if u_name == username: continue # Don't manage yourself
                
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**{u_name}** {'(BANNED)' if u_info.get('banned') else ''}")
                with col2:
                    # Ban Toggle
                    ban_label = "Unban" if u_info.get("banned") else "Ban"
                    if st.button(ban_label, key=f"ban_{u_name}"):
                        current_db["usernames"][u_name]["banned"] = not u_info.get("banned", False)
                        save_data(USER_FILE, current_db)
                        st.rerun()
                    # Delete
                    if st.button("🗑️", key=f"del_{u_name}"):
                        del current_db["usernames"][u_name]
                        save_data(USER_FILE, current_db)
                        st.rerun()

    if st.sidebar.button("Logout"):
        st.session_state.auth = {"status": False, "user": None, "is_admin": False}
        st.rerun()

    # --- CHAT INTERFACE ---
    st.title("Gemma 3 Chat")
    logs = load_data(LOG_FILE, {})
    if username not in logs: logs[username] = []
    
    for msg in logs[username]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if user_prompt := st.chat_input("Ask Gemma anything..."):
        with st.chat_message("user"):
            st.write(user_prompt)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logs[username].append({"time": timestamp, "role": "user", "content": user_prompt})

        try:
            with st.spinner("Gemma is thinking..."):
                response = requests.post(
                    OLLAMA_URL,
                    json={
                        "model": "gemma3:1b",
                        "prompt": user_prompt,
                        "stream": False
                    }
                )
                response.raise_for_status()
                answer = response.json().get("response", "No response.")
                
                with st.chat_message("assistant"):
                    st.write(answer)
                logs[username].append({"time": timestamp, "role": "assistant", "content": answer})
                save_data(LOG_FILE, logs)
        except Exception as e:
            st.error(f"Error connecting to Ollama: {e}")
