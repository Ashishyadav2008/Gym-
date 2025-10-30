import streamlit as st
import pandas as pd
import os
from datetime import datetime
from deepface import DeepFace
from PIL import Image
import smtplib
import json
from email.mime.text import MIMEText

# -----------------------------
# Setup and config load
# -----------------------------
os.makedirs("member_images", exist_ok=True)

for f in ["members.csv", "attendance.csv", "deleted_members.csv"]:
    if not os.path.exists(f):
        pd.DataFrame().to_csv(f, index=False)

with open("config.json", "r") as f:
    config = json.load(f)

GYM_EMAIL = config["gym_email"]
APP_PASS = config["app_password"]

# -----------------------------
# Helper functions
# -----------------------------
def send_email(to, subject, body):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = GYM_EMAIL
        msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GYM_EMAIL, APP_PASS)
            smtp.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email Error: {e}")
        return False

def load_members():
    try:
        return pd.read_csv("members.csv")
    except:
        return pd.DataFrame(columns=["ID","Name","Email","Mobile","Membership","Fee","ImagePath"])

def save_members(df):
    df.to_csv("members.csv", index=False)

def load_attendance():
    try:
        return pd.read_csv("attendance.csv")
    except:
        return pd.DataFrame(columns=["ID","Name","Date","EntryTime","ExitTime","Status"])

def save_attendance(df):
    df.to_csv("attendance.csv", index=False)

def try_verify_faces(img1, img2):
    try:
        result = DeepFace.verify(img1_path=img1, img2_path=img2, enforce_detection=False)
        return result["verified"], result.get("distance", 1.0), result
    except:
        return False, 1.0, None

# -----------------------------
# UI Layout
# -----------------------------
st.set_page_config(page_title="Gym Member System", layout="wide")
st.title("🏋️ Gym Member Management System")

menu = st.sidebar.radio("Navigation", [
    "Register Member",
    "Update / Delete Member",
    "Attendance – Entry",
    "Attendance – Exit",
    "View Members",
    "View Attendance",
    "Reset DB"
])

# -----------------------------
# Register Member
# -----------------------------
if menu == "Register Member":
    st.header("📝 Register New Member")

    name = st.text_input("Full Name")
    email = st.text_input("Email")
    mobile = st.text_input("Mobile No.")
    membership = st.selectbox("Membership Type", ["Monthly", "Quarterly", "Yearly"])
    fee = st.number_input("Fee (₹)", min_value=0)
    photo = st.camera_input("📷 Capture Member Face")

    if st.button("Register Member"):
        if not all([name, email, mobile, membership, photo]):
            st.warning("Please fill all fields and capture image.")
        else:
            members = load_members()
            new_id = len(members) + 1 if not members.empty else 1
            img_path = f"member_images/{new_id}_{name.replace(' ','_')}.jpg"
            img = Image.open(photo)
            img.save(img_path)

            new_data = pd.DataFrame([{
                "ID": new_id,
                "Name": name,
                "Email": email,
                "Mobile": mobile,
                "Membership": membership,
                "Fee": fee,
                "ImagePath": img_path
            }])
            members = pd.concat([members, new_data], ignore_index=True)
            save_members(members)

            send_email(email, "Gym Registration Successful",
                       f"Dear {name},\n\nWelcome to our Gym!\nYour Member ID: {new_id}\nMembership: {membership}\nFee: ₹{fee}\n\nStay Fit!\n- Gym Team")

            st.success(f"Member Registered! ID: {new_id}")
            st.image(img_path, caption="Saved Photo", width=200)

# -----------------------------
# Update / Delete Member
# -----------------------------
elif menu == "Update / Delete Member":
    st.header("✏️ Update or Delete Member")

    members = load_members()
    if members.empty:
        st.warning("No members registered yet.")
    else:
        ids = members["ID"].astype(str)
        selected_id = st.selectbox("Select Member ID", ids)
        member = members[members["ID"].astype(str) == selected_id].iloc[0]

        name = st.text_input("Full Name", member["Name"])
        email = st.text_input("Email", member["Email"])
        mobile = st.text_input("Mobile", member["Mobile"])
        membership = st.selectbox("Membership", ["Monthly","Quarterly","Yearly"], index=["Monthly","Quarterly","Yearly"].index(member["Membership"]))
        fee = st.number_input("Fee (₹)", min_value=0, value=int(member["Fee"]))

        if st.button("Update Member"):
            members.loc[members["ID"] == int(selected_id), ["Name","Email","Mobile","Membership","Fee"]] = [name,email,mobile,membership,fee]
            save_members(members)
            send_email(email, "Gym Details Updated", f"Dear {name}, your gym details have been updated successfully.\nMembership: {membership}\nFee: ₹{fee}")
            st.success("Member updated successfully.")

        if st.button("Delete Member"):
            del_member = members[members["ID"] == int(selected_id)]
            members = members[members["ID"] != int(selected_id)]
            save_members(members)

            deleted = pd.DataFrame(del_member)
            if not deleted.empty:
                pd.concat([pd.read_csv("deleted_members.csv", on_bad_lines='skip'), deleted], ignore_index=True).to_csv("deleted_members.csv", index=False)

            send_email(member["Email"], "Gym Membership Deleted",
                       f"Dear {member['Name']}, your gym membership (ID: {selected_id}) has been deleted from our records.")
            st.success("Member deleted successfully.")

# -----------------------------
# Attendance – Entry
# -----------------------------
elif menu == "Attendance – Entry":
    st.header("📥 Mark Entry")
    photo = st.camera_input("📷 Capture Face for Entry")

    if photo:
        img_path = "temp_entry.jpg"
        img = Image.open(photo)
        img.save(img_path)
        members = load_members()

        if members.empty:
            st.warning("No members registered.")
        else:
            matched_row, best_distance = None, 1.0
            progress = st.progress(0)
            for i, (_, row) in enumerate(members.iterrows(), 1):
                progress.progress(int(i / len(members) * 100))
                match, dist, _ = try_verify_faces(img_path, row["ImagePath"])
                if match and dist < best_distance:
                    matched_row, best_distance = row, dist
            progress.empty()

            if matched_row is not None:
                attendance = load_attendance()
                now = datetime.now()
                today = now.strftime("%Y-%m-%d")
                idstr = str(matched_row["ID"])

                exists = attendance[(attendance["ID"].astype(str) == idstr) & (attendance["Date"] == today)]
                if not exists.empty:
                    st.warning("Entry already marked today.")
                else:
                    new_entry = {
                        "ID": idstr,
                        "Name": matched_row["Name"],
                        "Date": today,
                        "EntryTime": now.strftime("%H:%M:%S"),
                        "ExitTime": "",
                        "Status": "Present"
                    }
                    attendance = pd.concat([attendance, pd.DataFrame([new_entry])], ignore_index=True)
                    save_attendance(attendance)
                    st.success(f"Entry marked for {matched_row['Name']}")
            else:
                st.error("No matching member found.")

# -----------------------------
# Attendance – Exit
# -----------------------------
elif menu == "Attendance – Exit":
    st.header("📤 Mark Exit")
    photo = st.camera_input("📷 Capture Face for Exit")

    if photo:
        img_path = "temp_exit.jpg"
        img = Image.open(photo)
        img.save(img_path)
        members = load_members()

        if members.empty:
            st.warning("No members registered.")
        else:
            matched_row, best_distance = None, 1.0
            progress = st.progress(0)
            for i, (_, row) in enumerate(members.iterrows(), 1):
                progress.progress(int(i / len(members) * 100))
                match, dist, _ = try_verify_faces(img_path, row["ImagePath"])
                if match and dist < best_distance:
                    matched_row, best_distance = row, dist
            progress.empty()

            if matched_row is not None:
                attendance = load_attendance()
                now = datetime.now()
                today = now.strftime("%Y-%m-%d")
                idstr = str(matched_row["ID"])

                mask = (attendance["ID"].astype(str) == idstr) & (attendance["Date"] == today)
                open_rows = attendance[mask & ((attendance["ExitTime"].isna()) | (attendance["ExitTime"] == ""))]

                if open_rows.empty:
                    st.warning("No open entry found for today.")
                else:
                    idx = open_rows.index[0]
                    attendance.at[idx, "ExitTime"] = now.strftime("%H:%M:%S")
                    attendance.at[idx, "Status"] = "Exited"
                    save_attendance(attendance)
                    st.success(f"Exit marked for {matched_row['Name']}")
            else:
                st.error("No matching member found.")

# -----------------------------
# View Members
# -----------------------------
elif menu == "View Members":
    st.header("👥 View Members")
    df = load_members()
    if df.empty:
        st.info("No members found.")
    else:
        st.dataframe(df)
        st.download_button("📄 Download Members CSV", df.to_csv(index=False), "members.csv")

# -----------------------------
# View Attendance
# -----------------------------
elif menu == "View Attendance":
    st.header("📋 View Attendance")
    df = load_attendance()
    if df.empty:
        st.info("No attendance records.")
    else:
        st.dataframe(df)
        st.download_button("📄 Download Attendance CSV", df.to_csv(index=False), "attendance.csv")

# -----------------------------
# Reset DB
# -----------------------------
elif menu == "Reset DB":
    st.header("⚠️ Reset Database")
    if st.button("Delete All Data (Danger)"):
        for f in ["members.csv", "attendance.csv", "deleted_members.csv"]:
            pd.DataFrame().to_csv(f, index=False)
        for img in os.listdir("member_images"):
            os.remove(os.path.join("member_images", img))
        st.success("All data reset successfully!")
