from unittest import mock

import requests
from pytest import param

HIGHWAY_DEDICATION_ITEMS = (
    "https://api.os.uk/features/ngd/ofa/v1/collections/"
    "trn-rami-highwaydedication-1/items/"
)
ROADLINK_ITEMS = (
    "https://api.os.uk/features/ngd/ofa/v1/collections/trn-ntwk-roadlink-5/items/"
)

AUTHORITY_ID = "esu4525_4348080549878_8"

ROADLINK_OSIDS = [
    "71dfa822-1506-458e-9e32-0b96024ff667",
    "850562e1-612c-4804-9b0f-9894ece65baa",
    "93639824-ee87-4f00-afce-6a1b2ddbbe9e",
    "d806896c-ee14-4446-977e-d525458bcf9a",
]

# A real dedication covering four Road Links across two Streets. The duplicated
# Road Link reference is how the API returns a link that spans both Streets.
DEDICATION = {
    "type": "Feature",
    "id": "40faf09d-f851-4172-9aca-5d27b519373c",
    "geometry": {
        "type": "LineString",
        "coordinates": [[-1.4598551, 54.8427213], [-1.459217, 54.8423274]],
    },
    "links": [{"href": f"{HIGHWAY_DEDICATION_ITEMS}40faf09d", "rel": "self"}],
    "properties": {
        "osid": "40faf09d-f851-4172-9aca-5d27b519373c",
        "authorityid": AUTHORITY_ID,
        "description": "All Vehicles",
        "publicrightofway": False,
        "nationalcycleroute": False,
        "quietroute": False,
        "obstruction": False,
        "planningorder": False,
        "worksprohibited": False,
        "highwaydedicationnetworkreference": [
            {"networkfeaturetype": "Street", "networkreferenceid": "38700490"},
            {"networkfeaturetype": "Road Link", "networkreferenceid": ROADLINK_OSIDS[0]},
            {"networkfeaturetype": "Street", "networkreferenceid": "38757990"},
            {"networkfeaturetype": "Road Link", "networkreferenceid": ROADLINK_OSIDS[1]},
            {"networkfeaturetype": "Road Link", "networkreferenceid": ROADLINK_OSIDS[2]},
            {"networkfeaturetype": "Road Link", "networkreferenceid": ROADLINK_OSIDS[3]},
            {"networkfeaturetype": "Road Link", "networkreferenceid": ROADLINK_OSIDS[3]},
        ],
    },
}

USRNS = ["38700490", "38757990"]

CLASSIFICATIONS = {
    osid: {"roadclassification": "Unclassified", "roadclassificationnumber": None}
    for osid in ROADLINK_OSIDS
}


def roadlink_feature(osid):
    """Builds a Road Link feature as the single-feature endpoint returns it."""
    return {
        "type": "Feature",
        "id": osid,
        "geometry": {
            "type": "LineString",
            "coordinates": [[-1.4599582, 54.8426948], [-1.4598482, 54.8427226]],
        },
        "properties": {
            "osid": osid,
            "roadclassification": "Unclassified",
            "roadclassificationnumber": None,
        },
        "links": [{"href": f"{ROADLINK_ITEMS}{osid}", "rel": "self"}],
    }


def http_errors(error_specs):
    """
    Turns ``{osid: [(status_code, retry_after), ...]}`` into queued HTTPErrors

    Built per call rather than stored in the parametrize table, since
    :func:`mock_ngd_get` consumes the queues as the requests are made.

    Args:
        error_specs (dict): Status codes to raise for each Road Link OSID, in order

    Returns:
        dict: Lists of HTTPError keyed by OSID, each carrying a response as
            ``raise_for_status`` would
    """
    errors = {}

    for osid, specs in error_specs.items():
        errors[osid] = []

        for status_code, retry_after in specs:
            response = requests.Response()
            response.status_code = status_code

            if retry_after:
                response.headers["Retry-After"] = retry_after

            errors[osid].append(requests.exceptions.HTTPError(response=response))

    return errors


def mock_ngd_get(url, roadlink_errors=None, **kwargs):
    """
    Stands in for `osdatahub.get`, dispatching on the requested collection

    Args:
        url (str): The requested URL
        roadlink_errors (dict, optional): Exceptions to raise on successive calls for
            a given Road Link OSID, from :func:`http_errors`, so a transient failure
            can be followed by a success

    Returns:
        Mock: A response exposing ``json()`` and ``raise_for_status()``
    """
    response = mock.Mock()

    if url.startswith(HIGHWAY_DEDICATION_ITEMS):
        response.json = lambda: {
            "type": "FeatureCollection",
            "features": [DEDICATION],
            "numberReturned": 1,
            "links": [],
        }
        return response

    osid = url.rsplit("/", 1)[-1]

    queued = (roadlink_errors or {}).get(osid)
    if queued:
        response.raise_for_status.side_effect = queued.pop(0)
        return response

    response.json = lambda: roadlink_feature(osid)
    return response


def test_roadlink_failures():
    test_variables = "error_specs, expected_osids, expected_sleeps"
    test_data = [
        param(
            {ROADLINK_OSIDS[0]: [(404, None)]},
            ROADLINK_OSIDS[1:],
            [],
            id="404-skipped-rest-kept",
        ),
        param(
            {ROADLINK_OSIDS[1]: [(429, "2"), (429, None)]},
            ROADLINK_OSIDS,
            # Retry-After wins first, then exponential backoff: 0.5 * 2**1.
            [2.0, 1.0],
            id="429-retried-until-it-clears",
        ),
    ]
    return test_variables, test_data


def test_roadlink_failures_raise():
    test_variables = "error_specs"
    test_data = [
        param({ROADLINK_OSIDS[1]: [(429, None)] * 3}, id="429-never-clears"),
        param({ROADLINK_OSIDS[2]: [(500, None)]}, id="500-server-error"),
        param({ROADLINK_OSIDS[2]: [(403, None)]}, id="403-forbidden"),
    ]
    return test_variables, test_data
