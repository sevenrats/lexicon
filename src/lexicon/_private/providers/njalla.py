"""Module provider for Njalla"""

import logging
from argparse import ArgumentParser
from typing import List

import requests

from lexicon.exceptions import AuthenticationError
from lexicon.interfaces import Provider as BaseProvider

LOGGER = logging.getLogger(__name__)


class Provider(BaseProvider):
    """Provider class for Njalla"""

    @staticmethod
    def get_nameservers() -> List[str]:
        return ["1-you.njalla.no", "2-can.njalla.in", "3-get.njalla.fo"]

    @staticmethod
    def configure_parser(parser: ArgumentParser) -> None:
        parser.add_argument("--auth-token", help="specify API token for authentication")

    def __init__(self, config):
        super(Provider, self).__init__(config)
        self.domain_id = None
        self.api_endpoint = "https://njal.la/api/1/"

    def authenticate(self):
        params = {"domain": self.domain}
        try:
            result = self._api_call("get-domain", params)
        except Exception as e:
            raise AuthenticationError(str(e))

        if result["name"] != self.domain:
            raise AuthenticationError("Domain not found")

        self.domain_id = self.domain

    def cleanup(self) -> None:
        pass

    # Create record. If record already exists with the same content, do nothing'
    def create_record(self, rtype, name, content, priority=None, weight=None, port=None):
        params = {
                "domain": self.domain,
                "type": rtype,
                "name": name,
                "content": content,
                "ttl": 60,
            }
        if rtype.lower() == 'srv':
            if any([x is None for x in [priority, weight, port]]):
                raise Exception("Priority, weight, and port are required to create SRV records.")
            params.update({
                "prio": int(priority),
                "weight": int(weight),
                "port": int(port),
            })
            
        if self._get_lexicon_option("ttl"):
            params["ttl"] = self._get_lexicon_option("ttl")
        result = self._api_call("add-record", params)

        LOGGER.debug("create_record: %s", result)
        return result

    # List all records. Return an empty list if no records found
    # type, name and content are used to filter records.
    # If possible filter during the query, otherwise filter after response is received.
    def list_records(
        self, rtype=None, name=None, content=None, priority=None, weight=None, port=None
    ):
        params = {"domain": self.domain}
        result = self._api_call("list-records", params)
        processed_records = []
        for record in result["records"]:
            new = {
                "id": record["id"],
                "type": record["type"],
                "name": self._full_name(record["name"]),
                "ttl": record["ttl"],
                "content": record["content"],
            }
            if record["type"].lower() == "srv":
                new.update({
                    'priority': record["prio"]
                    'weight': record["weight"]
                    'port': record['port']
                })
            processed_records.append(new)
        filtered_records = [
            record for record in processed_records
            if (
                (rtype is None or record["type"] == rtype)
                and (name is None or record["name"] == self._full_name(name))
                and (content is None or record["content"] == content)
                and (priority is None or record["priority"] == priority)
                and (weight is None or record["weight"] == weight)
                and (port is None or record["port"] == port)
            )
        ]
        LOGGER.debug("list_records: %s", filtered_records)
        return filtered_records

    # Create or update a record.
    def update_record(self, identifier, rtype=None, name=None, content=None):
        if not identifier:
            identifier = self._get_record_identifier(rtype=rtype, name=name)
        
        if rtype.lower()=="srv":
            raise Exception("Modifying SRV via API needs to be implemented.")

        params = {"id": identifier, "domain": self.domain, "content": content}
        result = self._api_call("edit-record", params)

        LOGGER.debug("update_record: %s", result)
        return result

    # Delete an existing record.
    # If record does not exist, do nothing.
    def delete_record(self, identifier=None, rtype=None, name=None, content=None):
        if not identifier:
            identifier = self._get_record_identifier(
                rtype=rtype, name=name, content=content
            )

        params = {"domain": self.domain, "id": identifier}
        self._api_call("remove-record", params)

        LOGGER.debug("delete_record: %s", True)
        return True

    # Helpers
    def _api_call(self, method, params):
        if self._get_provider_option("auth_token") is None:
            raise Exception("Must provide API token")

        data = {"method": method, "params": params}
        response = self._request("POST", "", data)

        if "error" in response.keys():
            error = response["error"]
            raise Exception("%d: %s" % (error["code"], error["message"]))

        return response["result"]

    def _get_record_identifier(self, rtype=None, name=None, content=None):
        records = self.list_records(rtype=rtype, name=name, content=content)
        if len(records) == 1:
            return records[0]["id"]

        raise Exception("Unambiguous record could not be found.")

    def _request(self, action="GET", url="/", data=None, query_params=None):
        if data is None:
            data = {}
        if query_params is None:
            query_params = {}
        token = self._get_provider_option("auth_token")
        headers = {
            "Authorization": "Njalla " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        response = requests.request(
            action,
            self.api_endpoint + url,
            headers=headers,
            params=query_params,
            json=data,
        )
        # if the request fails for any reason, throw an error.
        response.raise_for_status()
        return response.json()
