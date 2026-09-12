import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import google.generativeai as genai
import os
from streamlit_calendar import calendar

# --- Configuration & Setup ---
st.set_page_config(page_title="Household Hub", layout="wide", initial_sidebar_state="collapsed")
USERS = ["Logan", "Krystal", "Zoran", "N/A"]
CALENDAR_USERS = ["Logan", "Krystal", "Zoran", "Everyone"]

# Color coding for the calendar
USER_COLORS = {
    "Logan": "#3b82f6",     # Blue
    "Krystal": "#ec4899",   # Pink
    "Zoran": "#10b981",     # Green
    "Everyone": "#8b5cf6"   # Purple
}

# Set your API key in your terminal before running: export GEMINI_API_KEY="your_key"
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "SET_YOUR_API_KEY_HERE"))

CHORE_FILES = {
    "Daily": "Chores_Daily.csv",
    "Weekly": "Chores_Weekly.csv",
    "Monthly": "Chores_Monthly.csv",
    "To-Do": "Chores_To-Do.csv"
}
CALENDAR_FILE = "Calendar_Events.csv"

# --- Data Management ---
def load_and_upgrade_csv(filename, chore_type):
    """Loads CSVs and adds missing columns (like Status) for the new features."""
    required_cols = ["Task", "Assignees", "Instructions", "Media_Path", "Last_Completed", "Missed", "Status"]
    if chore_type == "To-Do":
        required_cols.append("Due_Date")
        
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        if len(df.columns) > 0 and 'Task' not in df.columns:
            df.rename(columns={df.columns[0]: 'Task'}, inplace=True)
            
        for col in required_cols:
            if col not in df.columns:
                if col == "Assignees":
                    df[col] = "[]"
                elif col == "Status":
                    df[col] = "Active"
                else:
                    df[col] = ""
        return df[required_cols]
    return pd.DataFrame(columns=required_cols)

def save_csv(df, filename):
    # Drop calculation columns before saving
    cols_to_drop = [col for col in ['Pending', 'Missed'] if col in df.columns]
    df.drop(columns=cols_to_drop, errors='ignore').to_csv(filename, index=False)

# --- Timing & Prioritization Logic ---
def evaluate_status(df, chore_type):
    if df.empty: return df
    
    today = pd.to_datetime(date.today())
    df['Last_Completed'] = pd.to_datetime(df['Last_Completed'], errors='coerce')
    
    if chore_type == "Daily":
        df['Pending'] = df['Last_Completed'].dt.date != today.date()
        df['Missed'] = df['Last_Completed'].dt.date < (today - pd.Timedelta(days=1)).date()
    elif chore_type == "Weekly":
        last_mon = today - pd.Timedelta(days=today.weekday())
        df['Pending'] = df['Last_Completed'] < last_mon
        df['Missed'] = df['Last_Completed'] < (last_mon - pd.Timedelta(weeks=1))
    elif chore_type == "Monthly":
        first_of_month = today.replace(day=1)
        df['Pending'] = df['Last_Completed'] < first_of_month
        df['Missed'] = df['Last_Completed'] < (first_of_month - pd.DateOffset(months=1))
    elif chore_type == "To-Do":
        df['Due_Date'] = pd.to_datetime(df['Due_Date'], errors='coerce')
        df['Pending'] = df['Last_Completed'].isna()
        df['Missed'] = (df['Due_Date'] < today) & df['Pending']

    return df.sort_values(by=['Missed', 'Pending'], ascending=[False, False])

# --- UI Components ---
st.title("🏡 Household Hub")

tabs = st.tabs(["📋 Chores", "📅 Calendar", "🛒 Shopping", "🤖 Gemini AI"])

# --- TAB 1: Chores ---
with tabs[0]:
    category = st.selectbox("Select Chore Category", ["Daily", "Weekly", "Monthly", "To-Do"])
    filename = CHORE_FILES[category]
    df = load_and_upgrade_csv(filename, category)
    df = evaluate_status(df, category)
    
    # Separate Active and On Hold chores
    active_df = df[df['Status'] != 'On Hold']
    hold_df = df[df['Status'] == 'On Hold']
    
    st.subheader(f"{category} Tasks")
    
    # Display Active Chores
    for index, row in active_df.iterrows():
        is_pending = row.get('Pending', True)
        is_missed = row.get('Missed', False)
        status_color = "🔴 OVERDUE" if is_missed else ("🟡 PENDING" if is_pending else "🟢 DONE")
        
        with st.expander(f"{row['Task']} - {status_color}"):
            cols = st.columns([2, 1, 1])
            
            with cols[0]:
                st.write("**Instructions:**", row['Instructions'] if pd.notna(row['Instructions']) else "None")
                
                # Action Buttons
                c1, c2 = st.columns(2)
                if c1.button("⏸️ Put on Hold", key=f"hold_{index}_{category}"):
                    df.at[index, 'Status'] = 'On Hold'
                    save_csv(df, filename)
                    st.rerun()
                if c2.button("🗑️ Delete", key=f"del_{index}_{category}"):
                    df = df.drop(index)
                    save_csv(df, filename)
                    st.rerun()
                
            with cols[1]:
                current_assignees = eval(row['Assignees']) if isinstance(row['Assignees'], str) and row['Assignees'].startswith('[') else []
                assignees = st.multiselect("Assignees", USERS, default=current_assignees, key=f"assign_{index}_{category}")
                if category == "To-Do":
                    due = st.date_input("Due Date", pd.to_datetime(row['Due_Date']) if pd.notna(row['Due_Date']) else date.today(), key=f"due_{index}")
            
            with cols[2]:
                st.file_uploader("Upload Image/Video", key=f"media_{index}_{category}")
                if st.button("✅ Mark Completed", key=f"complete_{index}_{category}", type="primary"):
                    df.at[index, 'Last_Completed'] = datetime.now()
                    df.at[index, 'Assignees'] = str(assignees)
                    if category == "To-Do": df.at[index, 'Due_Date'] = due
                    save_csv(df, filename)
                    st.rerun()

    # Add new chore form
    with st.form(f"add_chore_form_{category}"):
        st.subheader("Add New Chore")
        new_task = st.text_input("Task Name")
        new_instructions = st.text_area("Detailed Instructions")
        if st.form_submit_button("Add Chore"):
            new_row = {"Task": new_task, "Assignees": "[]", "Instructions": new_instructions, "Media_Path": "", "Last_Completed": "", "Missed": False, "Status": "Active"}
            if category == "To-Do": new_row["Due_Date"] = ""
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_csv(df, filename)
            st.rerun()

    # Display On Hold Chores
    if not hold_df.empty:
        st.divider()
        st.subheader("⏸️ Chores On Hold")
        for index, row in hold_df.iterrows():
            cols = st.columns([3, 1, 1])
            cols[0].write(f"**{row['Task']}**")
            if cols[1].button("▶️ Reactivate", key=f"reactivate_{index}_{category}"):
                df.at[index, 'Status'] = 'Active'
                save_csv(df, filename)
                st.rerun()
            if cols[2].button("🗑️ Delete", key=f"del_hold_{index}_{category}"):
                df = df.drop(index)
                save_csv(df, filename)
                st.rerun()

# --- TAB 2: Calendar ---
with tabs[1]:
    st.subheader("Family Calendar")
    
    if os.path.exists(CALENDAR_FILE):
        df_cal = pd.read_csv(CALENDAR_FILE)
    else:
        df_cal = pd.DataFrame(columns=["Title", "User", "Start_Date", "Start_Time", "End_Date", "End_Time"])

    # Calendar View
    events = []
    for _, row in df_cal.iterrows():
        start_str = f"{row['Start_Date']}T{row['Start_Time']}"
        end_str = f"{row['End_Date']}T{row['End_Time']}"
        events.append({
            "title": f"{row['User']}: {row['Title']}",
            "start": start_str,
            "end": end_str,
            "backgroundColor": USER_COLORS.get(row['User'], "#808080"),
            "borderColor": USER_COLORS.get(row['User'], "#808080")
        })

    calendar_options = {
        "headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth,timeGridWeek,timeGridDay"},
        "initialView": "dayGridMonth",
        "slotMinTime": "06:00:00",
        "slotMaxTime": "22:00:00"
    }
    
    calendar(events=events, options=calendar_options)

    # Add Event Form
    st.divider()
    with st.form("add_event_form"):
        st.subheader("Add Appointment")
        c_title = st.text_input("Event Title")
        c_user = st.selectbox("Assign To", CALENDAR_USERS)
        
        col1, col2 = st.columns(2)
        c_start_date = col1.date_input("Start Date")
        c_start_time = col1.time_input("Start Time")
        c_end_date = col2.date_input("End Date")
        c_end_time = col2.time_input("End Time")
        
        if st.form_submit_button("Add to Calendar"):
            new_event = {
                "Title": c_title, "User": c_user, 
                "Start_Date": c_start_date, "Start_Time": c_start_time.strftime("%H:%M:%S"),
                "End_Date": c_end_date, "End_Time": c_end_time.strftime("%H:%M:%S")
            }
            df_cal = pd.concat([df_cal, pd.DataFrame([new_event])], ignore_index=True)
            df_cal.to_csv(CALENDAR_FILE, index=False)
            st.rerun()

    # List & Delete Events
    if not df_cal.empty:
        with st.expander("Manage Existing Appointments"):
            for index, row in df_cal.iterrows():
                col1, col2 = st.columns([4, 1])
                col1.write(f"**{row['User']}** - {row['Title']} ({row['Start_Date']} at {row['Start_Time']})")
                if col2.button("🗑️ Delete", key=f"del_cal_{index}"):
                    df_cal = df_cal.drop(index)
                    df_cal.to_csv(CALENDAR_FILE, index=False)
                    st.rerun()

# --- TAB 3: Shopping Lists (Unchanged) ---
with tabs[2]:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Everyday Purchases")
        everyday_file = "Shopping_Everyday.csv"
        df_everyday = pd.read_csv(everyday_file) if os.path.exists(everyday_file) else pd.DataFrame(columns=["Item", "Where", "Priority"])
        st.dataframe(df_everyday, use_container_width=True)
        with st.form("add_everyday"):
            e_item = st.text_input("Item")
            e_loc = st.text_input("Where to Buy")
            e_pri = st.selectbox("Status", ["Urgent", "Wait for Sale", "Normal"])
            if st.form_submit_button("Add"):
                df_everyday.loc[len(df_everyday)] = [e_item, e_loc, e_pri]
                df_everyday.to_csv(everyday_file, index=False)
                st.rerun()

    with col2:
        st.subheader("Big Purchases (Saving up)")
        big_file = "Shopping_Big.csv"
        df_big = pd.read_csv(big_file) if os.path.exists(big_file) else pd.DataFrame(columns=["Item", "Target Amount", "Saved Amount"])
        st.dataframe(df_big, use_container_width=True)
        with st.form("add_big"):
            b_item = st.text_input("Goal Item")
            b_tar = st.number_input("Target Amount ($)", min_value=0.0)
            b_sav = st.number_input("Saved Amount ($)", min_value=0.0)
            if st.form_submit_button("Add"):
                df_big.loc[len(df_big)] = [b_item, b_tar, b_sav]
                df_big.to_csv(big_file, index=False)
                st.rerun()

# --- TAB 4: Gemini Integration ---
with tabs[3]:
    st.subheader("Ask Gemini for Chore Planning")
    st.write("Example: *'Give me a 20-minute chore list I can complete in the Kitchen.'*")
    
    user_prompt = st.text_input("What do you need help planning?")
    
    if st.button("Ask Gemini"):
        context = ""
        for cat, file in CHORE_FILES.items():
            temp_df = load_and_upgrade_csv(file, cat)
            active_tasks = temp_df[temp_df['Status'] == 'Active']['Task'].tolist() if not temp_df.empty else []
            context += f"{cat} Chores: {', '.join(active_tasks)}\n"
            
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"Here is the current active household chore list:\n{context}\n\nUser Request: {user_prompt}\nProvide a helpful, organized response."
            response = model.generate_content(prompt)
            st.write(response.text)
        except Exception as e:
            st.error("Make sure you have set a valid GEMINI_API_KEY environment variable. Error: " + str(e))
