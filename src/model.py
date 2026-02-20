import hashlib
import functools
import json
import typing
import abc
import os

import config_generated

ParamSet = typing.Sequence[typing.Mapping[str, typing.Any]]

class ParamsLoader(abc.ABC):
    @abc.abstractmethod
    def load_json(self, declared_path: str) -> ParamSet:
        pass

    @abc.abstractmethod
    def load_scad(self, declared_path: str) -> ParamSet:
        pass

    def load_and_merge(self, config: config_generated.ModelItem) -> ParamSet:
        combined = []

        def add(param, origin):
            param = dict(param)
            # if a parameter exists twice, drop the first one, but keep that default value.
            for i, existing in enumerate(combined):
                if existing["name"] == param["name"]:
                    combined.pop(i)
                    param["initial"] = existing["initial"]
                    break
            param["origin"] = origin
            combined.append(param)
        def add_all(params, origin):
            for p in params:
                add(p, origin)

        add_all(self.load_scad(config.file), "own")
        for path in config.additional_params:
            add_all(self.load_json(path), "additional")
        for path in config.additional_params_scad:
            add_all(self.load_scad(path), "additional")

        return combined

class Parameter:
    def __init__(self, definition: typing.Mapping[str, typing.Any], group: "GroupInfo"):
        self.definition = definition
        self.group = group
        self.metadata = config_generated.ParamMetadata()

    @property
    def name(self):
        return self.definition["name"]


class ScadContext:
    def __init__(
            self,
            config: config_generated.ModelItem,
            loader: ParamsLoader,
    ):
        self.config = config
        self.html_file = self.name() + ".html"
        self.link = self.html_file
        self.relative: str = ""  # Set later in main()

        definitions = loader.load_and_merge(config)
        groups = {}
        self.params = [
            Parameter(
                definition,
                groups.setdefault(definition["group"], GroupInfo(self, definition["group"]))
            ) for definition in definitions]
        for name, meta in config.param_metadata.items():
            for candidate in self.params:
                if name == candidate.name:
                    candidate.metadata = meta
                    break
            else:
                raise RuntimeError(f"Parameter {name} has declared metadata but not found in scad files for {self.config.file}")

    def name(self):
        return os.path.basename(self.config.file).removesuffix(".scad")

    def group(self, name: str) -> "GroupInfo":
        return GroupInfo(self, name)

class GroupInfo:
    def __init__(self, context: ScadContext, name: str):
        self.name = name
        self.config = context.config.tab_metadata.get(name, config_generated.TabMetadata())
        self.id = hashlib.sha256(name.encode("utf-8")).hexdigest()

    def __eq__(self, other):
        return self.name == other.name
