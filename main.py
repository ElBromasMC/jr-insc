import os
from copy import copy
import sys
import subprocess
import uuid
import shutil
import asyncio
import time
import datetime
import pytz
import numpy as np
import openpyxl
from io import BytesIO
from playwright.async_api import async_playwright
import pandas as pd

LIMIT_QUERY = sys.maxsize
MAIN_SHEET_NAME = "Data filtrada"
KEYWORDS = ["VENTANA", "MAMPARA", "MURO CORTINA", "VIDRIO"]

DATA_DIR  = os.environ.get("DATA_DIR", "./data")
TMP_DIR   = f"{DATA_DIR}/tmp"
EVD_DIR   = f"{DATA_DIR}/evidencias"
XLS_DIR   = f"{EVD_DIR}/xls"
IMG_DIR   = f"{EVD_DIR}/img"

SEACE_USER = os.environ.get("SEACE_USER", "")
SEACE_PASS = os.environ.get("SEACE_PASS", "")

#
# Util
#

def recreate_folder(path):
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            raise ValueError("Path exists but is not a directory")
    os.makedirs(path)

async def general_query_data_recursive(get_data, browser, year, start_date, end_date, opts):
    # Ensure the date range is valid
    if start_date > end_date:
        return pd.DataFrame()

    # Query data between start_date and end_date
    df = await get_data(browser, year, start_date, end_date, opts)
    
    # DEBUG
    print(f"general_query_data_recursive: {start_date} {end_date} {len(df)}")

    if len(df) < LIMIT_QUERY or start_date == end_date:
        return df
    
    # Calculate a midpoint date within the range.
    delta_days = (end_date - start_date).days
    mid_date = start_date + datetime.timedelta(days=delta_days // 2)
    
    # To avoid potential infinite recursion if the split doesn't reduce the range,
    # make sure the midpoint is strictly before the end_date.
    if mid_date >= end_date:
        return df

    # Recursively query the two halves of the date range.
    left_df = await general_query_data_recursive(get_data, browser, year, start_date, mid_date, opts)
    right_df = await general_query_data_recursive(get_data, browser, year, mid_date + datetime.timedelta(days=1), end_date, opts)
    
    # Concatenate the results from the two halves.
    return pd.concat([left_df, right_df], ignore_index=True)

#
# VIDRIOS
#

async def login_seace(page):
    print("login_seace: Iniciando sesión")
    await page.goto("https://prod1.seace.gob.pe/portal")
    await page.locator("[id=\"frmLogin\\:txtUsername\"]").fill(SEACE_USER)
    await page.locator("[id=\"frmLogin\\:txtPassword\"]").fill(SEACE_PASS)
    #await page.get_by_role("checkbox", name="Recordarme").click()
    await page.get_by_role("button", name="Acceder").click()
    await page.locator("[id=\"terminosCondiciones\\:idcheckBox\"]").click()
    await page.locator("[id=\"terminosCondiciones\\:idButtonAceptar\"]").click()
    await page.get_by_role("button", name="Aceptar").click()

async def logout_seace(page):
    print("logout_seace: Terminando sesión")
    await page.locator("[id=\"formIzquierdo\\:logout\"]").click()
    await page.get_by_role("button", name="Aceptar").click()

async def get_data_vidrios(browser, year, start_date, end_date, opts):
    filtro = opts.get("filter")
    print(f"get_data_vidrios: {filtro}")

    # Start page instance
    context = await browser.new_context()
    page = await context.new_page()

    # Web scraping
    await login_seace(page)

    await page.get_by_role("link", name="Buscar Procedimientos").click()
    await page.locator("#frmVisualizarRepresentantesPostor\\:pnlGrdBusquedaAvanzada2-1-3 > input").fill(filtro)
    await page.get_by_role("button", name="Buscar").click()

    try:
        # Download the results
        async with page.expect_download() as download_info:
            await page.get_by_title("Click para exportar un archivo excel").click(timeout=9000)
        download = await download_info.value
        filepath = f"{TMP_DIR}/{uuid.uuid4()}.xls"
        await download.save_as(filepath)

        # Read and process the file
        df = pd.read_excel(filepath)
        df = df[::-1].reset_index(drop=True)
    except Exception as e:
        await page.get_by_role("button", name="Aceptar").click()
        df = pd.DataFrame()
    finally:
        await logout_seace(page)
        await page.close()
        await context.close()

    return df

async def register_data_vidrios(browser, descripcion, name, i):
    print(f"register_data_vidrios: {i}")
    print(descripcion)

    # Start page instance
    context = await browser.new_context()
    page = await context.new_page()

    # Web scraping
    await login_seace(page)

    await page.get_by_role("link", name="Buscar Procedimientos").click()
    await page.locator("#frmVisualizarRepresentantesPostor\\:pnlGrdBusquedaAvanzada2-1-3 > input").fill(descripcion)
    await page.get_by_role("button", name="Buscar").click()

    try:
        await page.get_by_title("Ficha de Selección").click()
    except Exception as e:
        print(f"register_data_vidrios (Ficha de Selección) error: {e}")
        await page.screenshot(path=f"{IMG_DIR}/{name}/{i}-seleccion.png")
        try:
            await page.get_by_role("button", name="Aceptar").click()
        except Exception as e:
            pass
        await logout_seace(page)
        await page.close()
        await context.close()
        return "Error"

    try:
        await page.get_by_role("button", name="Registrar Participación").click(timeout=9000)
    except Exception as e:
        print(f"register_data_vidrios (Registrar Participación) error: {e}")
        await page.screenshot(path=f"{IMG_DIR}/{name}/{i}-registro.png")
        await logout_seace(page)
        await page.close()
        await context.close()
        return "No disponible"

    try:
        await page.get_by_role("checkbox").click()
    except Exception as e:
        print(f"register_data_vidrios (Checkbox) error: {e}")
        await page.screenshot(path=f"{IMG_DIR}/{name}/{i}-checkbox.png")
        try:
            await page.get_by_role("button", name="Aceptar").click()
        except Exception as e:
            pass
        await logout_seace(page)
        await page.close()
        await context.close()
        return "No disponible (Checkbox)"

    await page.get_by_role("button", name="Inscribir").click()
    await page.get_by_role("button", name="Aceptar").click()

    await logout_seace(page)
    await page.close()
    await context.close()
    return "Inscrito exitosamente"

async def query_vidrios_data(context, year, current_date):
    async def query_data_recursive(filter, start_date, end_date):
        return await general_query_data_recursive(get_data_vidrios, context, year, start_date, end_date, {"filter": filter})

    given_year = int(year)

    # Only proceed if given_year is less than or equal to current year
    if given_year > current_date.year:
        return pd.DataFrame()

    results = []
    for filter in KEYWORDS:
        start_date_given = datetime.date(given_year, 1, 1)
        end_date_given = current_date if given_year == current_date.year else datetime.date(given_year, 12, 31)
        df_part = await query_data_recursive(filter, start_date_given, end_date_given)
        results.append(df_part)

    df = pd.concat(results, ignore_index=True)
    return df

async def register_vidrios_data(browser, df, name):
    results = []
    for i, descripcion in enumerate(df["Descripción del Objeto"]):
        result = await register_data_vidrios(browser, descripcion, name, i)
        if result == "Error" and '\n' in descripcion:
            # Try again
            lines = descripcion.split('\n')
            longest = max(lines, key=len)
            result = await register_data_vidrios(browser, longest, name, i)
        results.append(result)
    df["Estado de registro"] = results
    return df

#
# Main
#

async def main():
    if len(SEACE_USER) == 0 or len(SEACE_PASS) == 0:
        print("main: SEACE_USER or SEACE_PASS are not set")
        sys.exit(1)

    if not os.path.isdir(DATA_DIR):
        raise FileNotFoundError(f"Directory {DATA_DIR} does not exist!")

    recreate_folder(TMP_DIR)
    os.makedirs(XLS_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)

    # Get date data
    timezone = pytz.timezone('America/Lima')
    now = datetime.datetime.now(timezone)
    current_date = now.date()
    datetime_name = now.strftime("%Y-%m-%d_%H-%M-%S")

    os.makedirs(f"{IMG_DIR}/{datetime_name}", exist_ok=True)

    async with async_playwright() as p:
        if os.environ.get("ENV") == "dev":
            browser = await p.chromium.launch(headless=False, args=['--ozone-platform=wayland'])
        else:
            browser = await p.chromium.launch(headless=True)

        # Inscripcion
        year = str(current_date.year)
        df = await query_vidrios_data(browser, year, current_date)
        df = await register_vidrios_data(browser, df, datetime_name)

        # Evidencia
        export_filepath = f"{XLS_DIR}/{datetime_name}.csv"
        df.to_csv(export_filepath, index=False)

        # Cleanup
        await browser.close()

asyncio.run(main())

