# -*- coding: utf8 -*-
# standard lib
import os, io
from pathlib import Path
from datetime import timedelta, datetime, timezone
from zoneinfo import ZoneInfo
import subprocess

# third-party lib
from osgeo import gdal, osr, ogr
import numpy as np
import netCDF4 as nc
# import xarray as xr


def get_ftp_url(local_dt):
    """
        基于时间戳生成ftp文件名和url
    :return: url
    """
    download_dt = local_dt - timedelta(hours=8)  
    year, month, day, hour, min = str(download_dt.year), str(download_dt.month).zfill(2), str(download_dt.day).zfill(2), str(download_dt.hour).zfill(2), str(download_dt.minute).zfill(2)
    url = f'ftp://13007129791_163.com:SP+wari8@ftp.ptree.jaxa.jp/pub/himawari/L2/PAR/021/{year}{month}/{day}/{hour}/H09_{year}{month}{day}_{hour}{min}_RFL021_FLDK.02801_02401.nc'
    return url 
    
# download nc from ftp
def downloadhtp(local_dt, save_dir):    
    """
        基于wget下载Java的ftp文件, 文件名基于时间戳生成
        eg: 
            wget -O G:/lcx/tmp.nc ftp://13007129791_163.com:SP+wari8@ftp.ptree.jaxa.jp/pub/himawari/L2/PAR/021/202602/28/09/H09_20260228_0900_RFL021_FLDK.02801_02401.nc
            wget -P G:/lcx/ ftp://13007129791_163.com:SP+wari8@ftp.ptree.jaxa.jp/pub/himawari/L2/PAR/021/202602/28/09/H09_20260228_0900_RFL021_FLDK.02801_02401.nc
        边界条件:
            文件延迟, 注意未更新文件下载反馈
    """
    url = get_ftp_url(local_dt)
    save_path = os.path.join(save_dir, os.path.basename(url))
    log_file = os.path.join(save_dir, "wget.log")
     
    cmd = ["wget", "-nv", "--timeout=30", "--tries=5", "--retry-connrefused", "--read-timeout=30",  "-O", save_path, "-o", log_file, url]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0: print(f"No data at {url}"); return None
    return save_path

def nc2tif(nc_path = './monthly/2022', var = 'SWR', tif_path = './monthly/2022_tif'):
    """
        将nc文件, 处理为tif文件
    """
    NC_DS = nc.Dataset(nc_path)
    # ['latitude', 'longitude', 'band_id', 'start_time', 'end_time', 'geometry_parameters', 'TAOT_02', 'TAAE', 'PAR', 'SWR', 'UVA', 'UVB', 'QA_flag']
    # print(f"nc文件变量: {NC_DS.variables.keys()}")
    lat_ds = NC_DS.variables['latitude'][:]
    lon_ds = NC_DS.variables['longitude'][:]
    var_ds = NC_DS.variables[var][:, :] # apply mask and fill_value, lat*lon
    data_to_write = var_ds.filled(np.nan)  # 将 masked array 转换为普通的 numpy array，缺失值用 np.nan 填充

    # 分辨率计算；影像的左上角&右下角坐标
    Lonmin, Latmax, Lonmax, Latmin = [lon_ds.min(), lat_ds.max(), lon_ds.max(), lat_ds.min()]
    Num_lat = len(lat_ds)
    Num_lon = len(lon_ds)
    lat_res = (Latmax - Latmin) / (float(Num_lat) - 1)
    lon_res = (Lonmax - Lonmin) / (float(Num_lon) - 1)

    # save as tif
    driver = gdal.GetDriverByName('GTiff')
    out_tif_name = tif_path
    out_tif = driver.Create(out_tif_name, Num_lon, Num_lat, 1, gdal.GDT_Float32, options=['COMPRESS=LZW'])
    geotransform = (Lonmin, lon_res, 0.0, Latmax, 0.0, -lat_res)
    out_tif.SetGeoTransform(geotransform)
    prj = osr.SpatialReference()
    prj.ImportFromEPSG(4326)
    out_tif.SetProjection(prj.ExportToWkt())
    out_band = out_tif.GetRasterBand(1)
    out_band.SetNoDataValue(float(var_ds.fill_value))  # 或其他
    out_band.WriteArray(data_to_write)
    out_tif.FlushCache()  # 将数据写入到硬盘
    out_tif = None  # 关闭tif文件

# crop nc and save as tif
def nc2tif_area(nc_path = './monthly/2022', var = 'SWR', tif_path = './monthly/2022_tif', lat_min = 20, lat_max = 50, lon_min = 100, lon_max = 130):
    """
        将nc文件, 裁剪为指定区域后处理为tif文件
    """
    # meteoinfo
    # ['latitude', 'longitude', 'band_id', 'start_time', 'end_time', 'geometry_parameters', 'TAOT_02', 'TAAE', 'PAR(umol/m^2/s)', 'SWR(W/m^2)', 'UVA', 'UVB', 'QA_flag']
    NC_DS = nc.Dataset(nc_path)
    # print(f"nc文件变量: {NC_DS.variables.keys()}")
    lat_ds = NC_DS.variables['latitude'][:]
    lon_ds = NC_DS.variables['longitude'][:]
    lon_res, lat_res= np.mean(np.diff(lon_ds)), abs(np.mean(np.diff(lon_ds)))

    # sub dataset
    lat_idx = np.where((lat_ds >= lat_min) & (lat_ds <= lat_max))[0]
    lon_idx = np.where((lon_ds >= lon_min) & (lon_ds <= lon_max))[0]
    lat_start, lat_end = lat_idx.min(), lat_idx.max()
    lon_start, lon_end = lon_idx.min(), lon_idx.max()
    data_area = NC_DS.variables[var][lat_start:lat_end + 1, lon_start:lon_end + 1]
    data_to_write = data_area.filled(np.nan) 
    lon_sub, lat_sub = lon_ds[lon_start:lon_end + 1], lat_ds[lat_start:lat_end + 1]
    Lonmin, Latmax = lon_sub.min(), lat_sub.max()

    # save to area_tif
    geotransform = (Lonmin, lon_res, 0.0, Latmax, 0.0, -lat_res)
    driver = gdal.GetDriverByName('GTiff')
    out_tif = driver.Create(tif_path, len(lon_sub), len(lat_sub), 1, gdal.GDT_Float32, options=['COMPRESS=LZW'])
    out_tif.SetGeoTransform(geotransform)
    prj = osr.SpatialReference()
    prj.ImportFromEPSG(4326)
    out_tif.SetProjection(prj.ExportToWkt())
    out_band = out_tif.GetRasterBand(1)
    out_band.SetNoDataValue(float(data_area.fill_value))  # 或其他
    out_band.WriteArray(data_to_write)
    # 设置 band 名称
    out_band.SetDescription(var)  
    out_band.SetMetadata({'long_name': var, 'units': 'W/m^2'})
    out_tif.FlushCache()  # 将数据写入到硬盘
    out_tif = None  # 关闭tif文件


if __name__ == "__main__":
    """
        下载 - 裁剪 - 保存并清理
        G:\miniconda3\envs\PV\python G:\lcx\Atmos\scripts\Himawari\archive_h8_realtime.py
    """
    #year, month, day, hour, min = 2026, 3, 2, 14, 30
    #cur_dt = datetime(year, month, day, hour, min, tzinfo=ZoneInfo("Asia/Shanghai"))
    all_dts = [(datetime.now()-timedelta(hours=h)).replace(minute=m, second=0, microsecond=0) for h in (1,0) for m in (0,10,20,30,40,50)][::-1]

    var = 'SWR'
    for cur_dt in all_dts:
        save_dir = Path('Archive')/cur_dt.strftime("%Y%m%d")
        save_dir.mkdir(parents=True, exist_ok=True)
        url = get_ftp_url(cur_dt)
        exists_path = os.path.join(save_dir, os.path.basename(url)).replace('.nc', f'_{var}_HaiNan.tif')
        if os.path.exists(exists_path): print(f"{exists_path} exists");continue    # file exists
            
        # (1) download nc from ftp
        nc_path = downloadhtp(cur_dt, save_dir)
        if nc_path is None: continue     # not Update
        
        # (2) nc裁剪并转tif
        hainan_area = [18, 20.5, 108, 111.5]  # [lat_min, lat_max, lon_min, lon_max]
        tif_path = nc_path.replace('.nc', f'_{var}_HaiNan.tif')
        nc2tif_area(nc_path=nc_path, var = var, tif_path=tif_path, lat_min=hainan_area[0], lat_max=hainan_area[1], lon_min=hainan_area[2], lon_max=hainan_area[3])
        os.remove(nc_path)
    
    # (3) 额外的nc处理, 例如裁剪后数据分析等
    # xs = xr.open_dataset(tif_path)    # import xarray as xr
    # rs = rioxarray.open_rasterio(tif_path)    # import rioxarray
    # breakpoint()
    # sub = ds.sel(lat=slice(lat1, lat2), lon=slice(lon1, lon2))
    
