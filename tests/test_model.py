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
