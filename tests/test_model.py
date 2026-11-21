import pytest
import model
import config_generated


class MockParamsLoader(model.ParamsLoader):
    def __init__(self, sets: dict[str, model.ParamSet]):
        self.sets = sets

    def load_json(self, declared_path: str) -> model.ParamSet:
        return self.sets[declared_path]

    def load_scad(self, declared_path: str) -> model.ParamSet:
        return self.sets[declared_path]


def test_merging():
    loader = MockParamsLoader({
        "model.scad": [
            {"name": "gridx", "initial": 1, "group": "Default"},
            {"name": "something", "group": "Default"}
        ],
        "include.scad": [
            {"name": "gridx", "initial": 2, "caption": "Grid X", "group": "Default"},
            {"name": "gridy", "initial": 3, "caption": "Grid Y", "group": "Default"},
        ]
    })
    ctx = model.ScadContext(
        config_generated.ModelItem.model_validate({
            "file": "model.scad",
            "additional-params-scad": ["include.scad"]
        }),
        loader
    )
    assert ctx.params[0].name == "something"
    assert ctx.params[1].name == "gridx"
    assert ctx.params[1].definition["initial"] == 1
    assert ctx.params[1].definition["caption"] == "Grid X"
    assert ctx.params[2].name == "gridy"
    assert ctx.params[2].definition["initial"] == 3
    assert ctx.params[2].definition["caption"] == "Grid Y"

def test_param_metadata_wildcard_order():
    loader = MockParamsLoader({
        "model.scad": [
            {"name": "magnet-orientation", "caption": "P0", "group": "Default"},
            {"name": "magnet-height", "caption": "P1", "group": "Default"},
            {"name": "magnet-diameter", "caption": "P2", "group": "Default"},
        ]
    })
    ctx = model.ScadContext(
        config_generated.ModelItem.model_validate({
            "file": "model.scad",
            "param-metadata": {
                "magnet-orientation": { "help-link": "fizz.com" },
                "*": { "help-link": "foo.com" },
                "magnet-diameter": { "help-link": "bar.com" }
            }
        }),
        loader
    )
    assert ctx.params[0].metadata.help_link == "foo.com"
    assert ctx.params[1].metadata.help_link == "foo.com"
    assert ctx.params[2].metadata.help_link == "bar.com"

def test_param_metadata_wildcard_match():
    loader = MockParamsLoader({
        "model.scad": [
            {"name": "magnet-orientation", "caption": "P0", "group": "Default"},
        ]
    })

    try:
        model.ScadContext(
            config_generated.ModelItem.model_validate({
                "file": "model.scad",
                "param-metadata": {
                    "foo-*": { "help-link": "foo.com" },
                }
            }),
            loader
        )
        assert False, "Expected exception"
    except RuntimeError:
        pass

    model.ScadContext(
        config_generated.ModelItem.model_validate({
            "file": "model.scad",
            "param-metadata": {
                "foo-*": { "help-link": "foo.com", "require-present": False },
            }
        }),
        loader
    )

def test_template_default():
    models = model.flatten_model_configs(config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model-template": { "default": { "description-extra-html": "foo" } },
        "model": [ { "file": "model.scad" } ]
    }))
    assert len(models) == 1
    assert models[0].description_extra_html == "foo"

def test_template_explicit_match():
    models = model.flatten_model_configs(config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model-template": { "tpl": { "description-extra-html": "foo" } },
        "model": [ { "file": "model.scad", "template": ["tpl"] } ]
    }))
    assert len(models) == 1
    assert models[0].description_extra_html == "foo"

def test_template_explicit_mismatch():
    models = model.flatten_model_configs(config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model-template": { "tpl": { "description-extra-html": "foo" } },
        "model": [ { "file": "model.scad" } ]
    }))
    assert len(models) == 1
    assert models[0].description_extra_html is None

def test_template_nest():
    models = model.flatten_model_configs(config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model-template": {
            "tpl": { "description-extra-html": "foo" },
            "tpl2": { "template": ["tpl"] }
        },
        "model": [ { "file": "model.scad", "template": ["tpl2"] } ]
    }))
    assert len(models) == 1
    assert models[0].description_extra_html == "foo"

def test_template_param_metadata():
    models = model.flatten_model_configs(config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model-template": {
            "bin": {
                "param-metadata": {
                    "foo": { "help-link": "foo.com" }
                }
            }
        },
        "model": [ { "file": "model.scad", "template": ["bin"] } ]
    }))
    assert len(models) == 1
    assert models[0].param_metadata["foo"].help_link == "foo.com"

def test_template_multi():
    models = model.flatten_model_configs(config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model-template": {
            "tpl": { "description-extra-html": "foo", "additional-params": ["fizz.json"] },
            "tpl2": { "additional-params": ["buzz.json"] }
        },
        "model": [ { "file": "model.scad", "template": ["tpl", "tpl2"] } ]
    }))
    assert len(models) == 1
    assert models[0].description_extra_html == "foo"
    assert models[0].additional_params == [ "fizz.json", "buzz.json"]

def test_preview_style_config():
    def style_value(model_config):
        value = model_config.preview_style
        return value.value if isinstance(value, config_generated.PreviewStyle) else value

    default_config = config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model": [ { "file": "model.scad" } ]
    })
    assert style_value(default_config.model[0]) is None

    colors_config = config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model": [ { "file": "model.scad", "preview-style": "colors" } ]
    })
    assert style_value(colors_config.model[0]) == "colors"

    models = model.flatten_model_configs(config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model-template": { "default": { "preview-style": "colors" } },
        "model": [ { "file": "model.scad" } ]
    }))
    assert style_value(models[0]) == "colors"


class CadqueryParamsLoader(MockParamsLoader):
    def load_scad(self, declared_path: str) -> model.ParamSet:
        raise AssertionError("OpenSCAD should not be used for CadQuery models")

    def load_cadquery(self, declared_path: str) -> model.ParamSet:
        return self.sets[declared_path]


def test_cadquery_runtime():
    ctx = model.ScadContext(
        config_generated.ModelItem.model_validate({
            "file": "bracket.py",
            "runtime": "cadquery",
            "param-metadata": {"lid.*": {"help-link": "https://example.com"}},
        }),
        CadqueryParamsLoader({"bracket.py": [
            {"name": "width", "type": "number", "initial": 10, "group": "Parameters"},
            {"name": "lid.height", "type": "number", "initial": 5, "group": "Lid"},
        ]}),
    )
    assert ctx.runtime == config_generated.Runtime.cadquery
    assert ctx.name() == "bracket"
    assert [p.name for p in ctx.params] == ["width", "lid.height"]
    assert ctx.params[1].group.name == "Lid"
    # Wildcards match dotted names
    assert ctx.params[1].metadata.help_link == "https://example.com"
    assert ctx.params[0].metadata.help_link is None


@pytest.mark.parametrize("option", ["additional-params", "additional-params-scad"])
def test_cadquery_rejects_additional_params(option):
    with pytest.raises(RuntimeError, match="not supported for CadQuery"):
        model.ScadContext(
            config_generated.ModelItem.model_validate({
                "file": "bracket.py",
                "runtime": "cadquery",
                option: ["params"],
            }),
            CadqueryParamsLoader({"bracket.py": []}),
        )


def test_runtime_config():
    configs = model.flatten_model_configs(config_generated.WebOpenscadEditorConfiguration.model_validate({
        "model-template": { "cq": { "runtime": "cadquery" } },
        "model": [
            { "file": "model.py" },
            { "file": "model.py", "template": ["cq"] },
            { "file": "model.scad", "template": ["cq"], "runtime": "openscad" },
        ]
    }))
    # No detection from the file extension
    assert model.model_runtime(configs[0]) == config_generated.Runtime.openscad
    assert model.model_runtime(configs[1]) == config_generated.Runtime.cadquery
    assert model.model_runtime(configs[2]) == config_generated.Runtime.openscad
