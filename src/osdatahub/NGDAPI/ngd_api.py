import json
from datetime import datetime
from os import environ
from typing import Union
import logging

import requests
from geojson import FeatureCollection, Feature
from typeguard import check_argument_types

from osdatahub import Extent
from osdatahub.NGDAPI.ngd_collections import validate_collection, get_collection, Collection
from osdatahub.NGDAPI.crs import get_crs
from osdatahub.errors import raise_http_error


def merge_geojsons(gj1, gj2):
    if not (gj1 or gj2):
        raise ValueError("Inputs were both empty")
    elif not gj1:
        return gj2
    elif not gj2:
        return gj1

    gj1["features"] += gj2["features"]
    gj1["numberReturned"] += gj2["numberReturned"]
    gj1["links"] += gj2["links"]

    return gj1


class NGDAPI:
    __ENDPOINT = r"https://api.os.uk/features/ngd/ofa/v1/collections"

    def __init__(self, key: str, collection: str, extent: Extent = None):
        self.key: str = key
        self.collection: str = collection
        self.extent = extent

    def __endpoint(self, feature_id=None) -> str:
        return f"{self.__ENDPOINT}/{self.collection}/items/{feature_id if feature_id else ''}"

    @classmethod
    def get_collections(cls) -> dict:
        response = requests.get(cls.__ENDPOINT)
        response.raise_for_status()
        return response.json()

    def query(self,
              extent: Extent = None,
              crs: Union[str, int] = None,
              start_datetime: datetime = None,
              end_datetime: datetime = None,
              cql_filter: str = None,
              filter_crs: Union[str, int] = None,
              max_results: int = 100,
              limit: int = 100,
              offset: int = 0) -> FeatureCollection:

        assert check_argument_types()

        params = {}

        # Checking validity and preformatting arguments
        if crs:
            params["crs"] = get_crs(crs=crs)

        if extent:
            params["bbox"] = extent.bbox
            params["bbox-crs"] = get_crs(extent.crs, valid_crs=("epsg:4326", "epsg:27700", "epsg:3857", "crs84"))

        if start_datetime or end_datetime:
            if start_datetime and end_datetime and start_datetime > end_datetime:
                raise ValueError("Start time must be before end time")

            start_datetime = start_datetime.isoformat() + "Z" if start_datetime else ".."
            end_datetime = end_datetime.isoformat() + "Z" if end_datetime else ".."

            params["datetime"] = f"{start_datetime}/{end_datetime}"

        if cql_filter:
            params['filter'] = cql_filter
            if filter_crs:
                params['filter-crs'] = get_crs(crs=filter_crs, valid_crs=("epsg:4326", "epsg:27700", "epsg:3857",
                                                                          "crs84"))

        if limit > 100:
            logging.warning(f"Limit cannot be more than 100 but has value {limit}. Setting to 100")
            limit = 100

        n_required = max_results

        data = {}

        while n_required > 0:
            offset = max(offset, data["numberReturned"] if "numberReturned" in data else 0)
            params.update({"limit": limit, "offset": offset})
            try:
                response = requests.get(self.__endpoint(), params=params, headers={"key": self.key})
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                logging.error(json.dumps(e.response.json(), indent=4))
                raise e

            resp_json = response.json()

            data = merge_geojsons(data, resp_json)

            if resp_json["numberReturned"] < limit:
                break
            else:
                n_required -= resp_json["numberReturned"]

        return data

    def query_feature(self, feature_id: str, crs: Union[str, int] = "CRS84") -> Feature:

        crs = get_crs(crs)

        response = requests.get(self.__endpoint(feature_id), params={"crs": crs}, headers={"key": self.key})
        response.raise_for_status()

        return response.json()


if __name__ == '__main__':
    coll = "bld-fts-buildingline"
    key = environ.get("OS_API_KEY")
    ngd = NGDAPI(key, coll)
    print(json.dumps(ngd.query_feature("00003b73-ab7d-4fc4-bedf-ac91830400a1"), indent=4))