# standard lib
from datetime import datetime, timedelta, timezone
import os
import re
from io import BytesIO
import time
from pathlib import Path
import subprocess

# thirdy party lib
from osgeo import gdal
import xarray as xr
import rioxarray
import pandas as pd
import requests
import rasterio
from rasterio.merge import merge
from tqdm import tqdm
import matplotlib.pyplot as plt

# internal lib
host = os.getenv("DB_HOST")
pwd = os.getenv("DB_PWD")
if not host or not pwd:
    raise RuntimeError("DB credentials not set")
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus   
host, port, usr, pwd, database = host, 5432, 'postgres', pwd, 'ZHGF'
url = f"postgresql+psycopg2://{usr}:{quote_plus(pwd)}@{host}:{port}/{database}"
engine = create_engine(url, pool_recycle=3600)

if __name__ == "__main__":

    # update data from github. local
    #repo_dir = r'G:\lcx\Atmos\repo\Himawari_radiation_api'
    #update_repo(repo_dir)

    table_name, site_name = 'swr_himawari_github', '万宁礼纪'
    sql = text(f'''SELECT *FROM '{table_name}' WHERE "time" >= :start AND "time" < :end AND "name" = :name''')
    sql = text(f''' SELECT * FROM "{table_name}" WHERE "name" = :name ORDER BY "time" DESC LIMIT 1''')
    server_lasted_df = pd.read_sql_query(sql, engine,params={"name": site_name}, index_col="time")

    archive_dir = Path('Archive')
    date_list = pd.date_range(start=server_lasted_df.index[0].date(), end=datetime.now(timezone.utc).date(), freq='D').strftime("%Y%m%d").tolist()
    # date_list = sorted(os.listdir(archive_dir))
    wn_ll = [18.708079, 110.295539]
    values, times = [], []
    for date in tqdm(date_list):
        date_dir = os.path.join(archive_dir, date)
        file_list = [os.path.join(date_dir, fp) for fp in os.listdir(date_dir)]
        for fp in file_list:
            with rasterio.open(fp) as src:
                row, col = src.index(wn_ll[1], wn_ll[0])
                val = src.read(1)[row, col]
                values.append(val)
            times.append(pd.to_datetime(re.search(r'_(\d{8}_\d{4})_', fp).group(1), format="%Y%m%d_%H%M", utc=True))
            
    df = pd.DataFrame({"SWR": values}, index=pd.DatetimeIndex(times))
    df_bj = df.tz_convert("Asia/Shanghai")
    df_bj.name = 'time'
    df_bj['name'] = '万宁礼纪'
    
    upload_df = df_bj[df_bj.index > server_lasted_df.tz_convert("Asia/Shanghai").index[0]]
    upload_df.to_sql(table_name, con=engine, if_exists="append", index=True)
    print(upload_df.iloc[[-1, 1]])
