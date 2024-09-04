import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
from datetime import datetime, timedelta

def extract_table_data_from_text(text, current_date):
    data = []

    lines = text.split('\n')
    st.write("Text extracted from PDF:")
    st.write(lines)

    for line in lines:
        line = line.strip()
        if not line:
            continue

        date_match = re.match(r'^\d{2}/\d{2}/\d{4}', line)
        if date_match:
            current_date = date_match.group(0)
            current_date = pd.to_datetime(current_date, format='%d/%m/%Y').strftime('%d/%m/%Y')
            continue

        if not current_date:
            continue

        user_id_match = re.search(r'\b[A-Za-z0-9]{4,}\b', line)
        punch_time_match = re.search(r'\d{2}:\d{2}:\d{2}', line)
        io_type_match = re.search(r'\bIN\b|\bOUT\b', line)

        user_id = user_id_match.group(0).strip() if user_id_match else ''
        punch_time = punch_time_match.group(0).strip() if punch_time_match else ''
        io_type = io_type_match.group(0).strip() if io_type_match else ''

        if user_id:
            name_start = line.find(user_id) + len(user_id)
            name_end = line.find(punch_time) if punch_time else len(line)
            name = line[name_start:name_end].strip()
            name = re.sub(r'\bIN\b|\bOUT\b', '', name).strip()

            if punch_time:
                data.append([current_date, user_id, name, punch_time, io_type])

    return data, current_date

def pdf_to_excel(pdf_file):
    all_data = []
    current_date = None

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            st.write(f"Text from page {page.page_number}:")
            st.write(text)

            if text:
                page_data, current_date = extract_table_data_from_text(text, current_date)
                if page_data:
                    all_data.extend(page_data)
            else:
                st.write("No text extracted from page.")

    if all_data:
        result_df = pd.DataFrame(all_data, columns=['Date', 'User ID', 'Name', 'Punch Time', 'I/O Type'])
        return result_df
    else:
        return pd.DataFrame()

def process_shift_data(df, date_col, punch_time_col, io_type_col, user_id_col, name_col):
    df['DateTime'] = pd.to_datetime(df[date_col].astype(str) + ' ' + df[punch_time_col].astype(str), format="%d/%m/%Y %H:%M:%S", errors='coerce')
    df.dropna(subset=['DateTime'], inplace=True)

    evening_start_time = datetime.strptime('17:00:00', '%H:%M:%S').time()
    night_end_time = datetime.strptime('02:15:00', '%H:%M:%S').time()

    all_data = []
    df = df.sort_values(by=[user_id_col, 'DateTime'])

    for user, user_df in df.groupby(user_id_col):
        user_data = []
        current_shift = []
        previous_logout_date = None

        for _, row in user_df.iterrows():
            current_time = row['DateTime'].time()
            current_date = row['DateTime'].date()

            if current_time >= evening_start_time:
                if previous_logout_date and current_date > previous_logout_date:
                    next_day_data = user_df[user_df['DateTime'].dt.date == current_date]
                    if not next_day_data.empty:
                        previous_row = next_day_data.iloc[0]
                        current_shift.append(previous_row)
                    previous_logout_date = None

                if current_time <= night_end_time:
                    current_date += timedelta(days=1)
                row[date_col] = current_date.strftime('%d/%m/%Y')
                current_shift.append(row)

            else:
                if current_shift:
                    user_data.append(current_shift)
                current_shift = [row]

            if row[io_type_col] == 'OUT':
                previous_logout_date = row['DateTime'].date()

        if current_shift:
            user_data.append(current_shift)

        for shift in user_data:
            shift_start_date = shift[0]['DateTime'].date()
            shift_end_date = shift[-1]['DateTime'].date()

            for i, record in enumerate(shift):
                if i > 0 and shift[i-1][io_type_col] == 'OUT' and record[io_type_col] == 'IN':
                    if shift[i-1]['DateTime'].date() != record['DateTime'].date():
                        shift_end_date = record['DateTime'].date()

                shift_date = shift_start_date if record[date_col] == shift[0][date_col] else shift_end_date

                all_data.append({
                    'Date': shift_date.strftime('%d/%m/%Y'),
                    'User ID': user,
                    'Name': record[name_col],
                    'Punch Time': record[punch_time_col],
                    'I/O Type': record[io_type_col],
                    'Shift Start': shift_start_date,
                    'Shift End': shift_end_date
                })

    final_df = pd.DataFrame(all_data)
    return final_df

def identify_columns(df):
    date_col = next((col for col in df.columns if re.search(r'\bdate\b', col, re.IGNORECASE)), None)
    punch_time_col = next((col for col in df.columns if re.search(r'\bpunch\s*time\b', col, re.IGNORECASE)), None)
    io_type_col = next((col for col in df.columns if re.search(r'\bi\s*/\s*o\s*type\b', col, re.IGNORECASE)), None)
    user_id_col = next((col for col in df.columns if re.search(r'\buser\s*id\b', col, re.IGNORECASE)), None)
    name_col = next((col for col in df.columns if re.search(r'\bname\b', col, re.IGNORECASE)), None)
    return date_col, punch_time_col, io_type_col, user_id_col, name_col

def main():
    st.title("PDF to Excel Converter and Data Organizer")

    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

    if uploaded_file:
        st.write("Processing your file...")

        # Convert PDF to Excel
        result_df = pdf_to_excel(uploaded_file)

        if not result_df.empty:
            st.write("Data extracted successfully!")
            st.dataframe(result_df)

            # Process and organize the data
            date_col, punch_time_col, io_type_col, user_id_col, name_col = identify_columns(result_df)

            if all([date_col, punch_time_col, io_type_col, user_id_col, name_col]):
                organized_df = process_shift_data(result_df, date_col, punch_time_col, io_type_col, user_id_col, name_col)

                if not organized_df.empty:
                    st.write("Organized Data by Day and User:")
                    st.dataframe(organized_df)

                    # Save the DataFrame to Excel and provide download link
                    excel_buffer = BytesIO()
                    organized_df.to_excel(excel_buffer, index=False, engine='openpyxl')
                    excel_buffer.seek(0)

                    st.download_button(
                        label="Download Organized Data",
                        data=excel_buffer,
                        file_name="organized_data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.write("No data was organized based on the provided criteria.")
            else:
                st.error("The uploaded file does not contain the required columns.")
        else:
            st.write("No data found in the PDF.")

if __name__ == "__main__":
    main()
