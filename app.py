import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random, string, requests
from datetime import datetime, timedelta

# --- CONFIGURATION ---
OLLAMA_URL = "https://chanell-uninspirable-factually.ngrok-free.dev/api/generate" # Update this if using a tunnel
ADMIN_CODE = st.secrets.get("ADMIN_CODE", "E42B455") # Set this in Cloud Secrets

# --- DATABASE CONNECTION (Google Sheets) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_db():
    # Load users from the 'users' worksheet
    return conn.read(worksheet="users", ttl=0).dropna(how="all")

def save_db(df):
    conn.update(worksheet="users", data=df)

def get_logs(username):
    df = conn.read(worksheet="logs", ttl=0).dropna(how="all")
    return df[df['username'] == username].to_dict('records')

def add_log(username, role, content):
    df = conn.read(worksheet="logs", ttl=0).dropna(how="all")
    new_log = pd.DataFrame([{
        "username": username,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "role": role,
        "content": content
    }])
    updated_df = pd.concat([df, new_log], ignore_index=True)
    conn.update(worksheet="logs", data=updated_df)

# --- AUTHENTICATION LOGIC ---
if "auth" not in st.session_state:
    st.session_state.auth = {"status": False, "user": None, "is_admin": False}

db_df = get_db()

# --- LOGIN/SIGNUP UI ---
if not st.session_state.auth["status"]:
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")
        if st.button("Login"):
            user_row = db_df[db_df['username'] == u]
            if not user_row.empty:
                if user_row.iloc[0]['banned']:
                    st.error("🚫 Account Banned.")
                elif str(user_row.iloc[0]['password']) == p:
                    st.session_state.auth = {
                        "status": True, 
                        "user": u, 
                        "is_admin": bool(user_row.iloc[0]['is_admin'])
                    }
                    st.rerun()
            st.error("Invalid credentials")

    with tab2:
        is_first = len(db_df) == 0
        new_u = st.text_input("New Username")
        new_p = st.text_input("New Password", type="password")
        s_code = st.text_input("Signup Code") if not is_first else None
        
        if st.button("Create Account"):
            if not db_df[db_df['username'] == new_u].empty:
                st.error("Username taken")
            elif is_first or s_code == ADMIN_CODE: # Using Admin Code as simple bypass for now
                new_row = pd.DataFrame([{
                    "username": new_u, "password": new_p, 
                    "is_admin": is_first, "banned": False
                }])
                save_db(pd.concat([db_df, new_row], ignore_index=True))
                st.success("Account created! Log in.")
            else:
                st.error("Invalid Code")

# --- MAIN APP ---
else:
    username = st.session_state.auth["user"]
    st.sidebar.title(f"Hi, {username}")

    # ADMIN PANEL (Banning/Deleting)
    if st.session_state.auth["is_admin"]:
        with st.sidebar.expander("🛠️ User Management"):
            current_db = get_db()
            for _, row in current_db.iterrows():
                if row['username'] == username: continue
                c1, c2 = st.columns([2,1])
                c1.write(f"{row['username']} {'(B)' if row['banned'] else ''}")
                if c2.button("Toggle", key=f"ban_{row['username']}"):
                    current_db.loc[current_db['username'] == row['username'], 'banned'] = not row['banned']
                    save_db(current_db)
                    st.rerun()

    if st.sidebar.button("Logout"):
        st.session_state.auth = {"status": False, "user": None, "is_admin": False}
        st.rerun()

    # CHAT INTERFACE
    st.title("Gemma 3 Chat")
    history = get_logs(username)
    
    for msg in history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Ask Gemma..."):
        with st.chat_message("user"):
            st.write(prompt)
        add_log(username, "user", prompt)

        try:
            with st.spinner("Thinking..."):
                resp = requests.post(OLLAMA_URL, json={"model": "gemma3:1b", "prompt": prompt, "stream": False})
                answer = resp.json().get("response", "No response.")
                with st.chat_message("assistant"):
                    st.write(answer)
                add_log(username, "assistant", answer)
        except Exception as e:
            st.error(f"Ollama Error: {e}")
