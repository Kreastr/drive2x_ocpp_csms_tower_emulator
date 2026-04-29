from pathlib import Path
from typing import Optional

import yaml
from anytree import findall
from nicegui import ui, context
from slugify import slugify

from .models.figma_document_model import FigmaNode, NodeType, Color, LayoutMode, Constraint, StyleInfo, TextCase


class FigmaRenderer():
    
    def __init__(self, project_file : Path = Path("project.yaml")):
        self.all_screens = dict()
        with open(project_file) as f:
            d = yaml.load(f, Loader=yaml.SafeLoader)
            dd=FigmaNode.model_validate(d)
            dd.update_parents(forced_svg={"Livello_1",
                                          "D2X_LOGO_darkBG_COMPACT 1",
                                          "Vector",
                                          "PAVIMENTO",
                                          "Livello 2",
                                          "GRAPHIC_CAR_CHARGING"})
            #for pre, _, node in RenderTree(dd):
            #    print(f"{pre}{node.name} <{node.type}>")

            screens = findall(dd, filter_=FigmaRenderer.screen_condition)
            # export_screens_to_yaml(screens)
            self.all_screens = FigmaRenderer.export_screens_to_dict(screens)
            self.render_header()

    @staticmethod
    def render_header():
        ui.add_head_html(r'''
        <style>
        @font-face{
            font-family: "Raleway";
            src: url('/d2x_ui/static/fonts/Raleway-VariableFont_wght.ttf ') format('truetype');
            font-weight: normal;
            font-style: normal;
        }
        </style>
        <meta name="viewport" content= "width=device-width, user-scalable=no"/>
        <script>
        function emitSize() {
            const scale = Math.min(window.innerWidth / 1080, window.innerHeight / 1920);
            document.querySelector(".nicegui-content").style.setProperty("--scale", scale);
            let offset = 0;
            if (window.innerWidth > (scale*1080)) {
                offset = (window.innerWidth - (scale*1080));
            }
            document.querySelector(".nicegui-content").style.setProperty("--offset", ""+offset+"px");
        }
        window.onload = emitSize;
        window.onresize = emitSize;
        </script>
        ''', shared=True)

    @staticmethod
    def get_unique_name(base_name : str, names : set):
        if base_name not in names:
            names |= {base_name}
            return base_name, names
        i = 2
        while True:
            candidate = f"{base_name}_{i}"
            if candidate not in names:
                names |= {candidate}
                return candidate, names
            i += 1

    @staticmethod
    def screen_condition(n : FigmaNode):
        return n.type in [NodeType.Frame, NodeType.Instance] and n.parent.name.upper() == "AIRPORT OVERVIEW"

    @staticmethod
    def export_screens_to_yaml(screens):
        names = set()
        for s in screens:

            name, names = FigmaRenderer.get_unique_name(slugify(s.name, separator="_"), names)
            print(s.name, name, s.id)
            with open(f"{name}.yaml", "w") as fr:
                yaml.dump(s.model_dump(exclude_none=True), fr)

    @staticmethod
    def export_screens_to_dict(screens):
        names = set()
        export = {}
        for s in screens:

            name, names = FigmaRenderer.get_unique_name(slugify(s.name, separator="_"), names)
            export[name] = s
            print(name)
        return export


    @staticmethod
    def rgba_color(backgroundColor : Color):
        return (f"rgba({backgroundColor.r * 255}," +
                f"{backgroundColor.g * 255}," +
                f"{backgroundColor.b * 255}," +
                f"{backgroundColor.a * 255})")

    @staticmethod
    def rgb_color(backgroundColor : Color):
        return (f"rgb({int(backgroundColor.r * 255)}," +
                f"{int(backgroundColor.g * 255)}," +
                f"{int(backgroundColor.b * 255)})")


    @staticmethod
    def split_spans(text, indices):
        spans = []
        if len(indices):
            current_idx = indices[0]
            substring = ""
            for c, idx in zip(text, indices):
                if idx == current_idx:
                    substring += c
                else:
                    spans.append(dict(text=substring, style=current_idx))
                    current_idx = idx
                    substring = c
            spans.append(dict(text=substring, style=current_idx))
        else:
            spans.append(dict(text=text, style=0))
        return spans


    @staticmethod
    def add_newline_breaks(text):
        for separator in ["\n", "\u2028"]:
            text = "<br/>".join(text.split(separator))
        return text

    @staticmethod
    def font_style_map(d):
        key_rename = {"fontFamily": "font-family",
                      "fontSize": "font-size",
                      "fontWeight": "font-weight",
                      "fontStyle": "font-style",
                      "textDecoration": "text-decoration"}
        k, v = d
        k2 = k
        v2 = v
        if k in key_rename:
            k2 = key_rename[k]
        if k == "fills":
            assert len(v) == 1
            if 'color' in v[0]:
                k2 = "color"
                v2 = FigmaRenderer.rgba_color(Color.model_validate(v[0]['color']))
        return k2, v2

    @staticmethod
    def format_spans(raw_text, styleOverrideTable):
        for d in raw_text:
            style=""
            style_data = {}
            styleId = str(d['style'])
            if styleId != '0' and styleId in styleOverrideTable:
                style_data = styleOverrideTable[styleId]
                for k, v in map(FigmaRenderer.font_style_map, style_data.items()):
                    style += f"{k}: {v}; "

            print("span", FigmaRenderer.add_newline_breaks(d['text']), style)
            ui.html(FigmaRenderer.add_newline_breaks(d['text']), tag="span").style(style) # , sanitize=False


    @staticmethod
    def render_node(current_node : FigmaNode,
                    skip_footers=False,
                    parent_node=None,
                    parent_container=False):

        current_element = None
        me_containter = False

        absolute_position = False
        if skip_footers and current_node.name == "Footer":
            return

        if current_node.visible is not None:
            if not current_node.visible:
                return

        classes = ""

        if current_node.type is NodeType.Text:
            raw_text = [dict(text=current_node.characters, style=0)]
            if current_node.characterStyleOverrides is not None:
                raw_text = FigmaRenderer.split_spans(raw_text[0]["text"], current_node.characterStyleOverrides)
            if len(raw_text) == 1:
                current_element = ui.label(text=raw_text[0]["text"])
            else:
                current_element = ui.element()
                with current_element:
                        FigmaRenderer.format_spans(raw_text, current_node.styleOverrideTable)
            print("TEXT", current_node.name, current_node)
        elif current_node.type in [NodeType.Frame, NodeType.Group, NodeType.Instance]:

            kwargs = {}
            if current_node.layoutMode is None:
                element = ui.element
                kwargs["tag"] = "div"
            elif current_node.layoutMode is LayoutMode.Vertical:
                element = ui.column
                me_containter = True
                kwargs["align_items"] = "center"
                classes += " justify-center "
            elif current_node.layoutMode is LayoutMode.Horizontal:
                element = ui.row
                me_containter = True
                kwargs["align_items"] = "center"
                classes += " justify-center "
            else:
                raise NotImplementedError(f"Missing handling for layoutMode {current_node.layoutMode}")


            if element:
                current_element = element(**kwargs).classes(classes)
                with current_element:
                    for c in current_node.children:
                        FigmaRenderer.render_node(c,
                                                  skip_footers=skip_footers,
                                                  parent_node=current_node,
                                                  parent_container=me_containter)

        elif current_node.type in [NodeType.Svg]:
            for candidate in [".svg", ".png"]:
                if Path("static/images/"+current_node.name+candidate).exists():
                    current_element = ui.image("static/images/"+current_node.name+candidate)
                    break
        else:
            raise NotImplementedError(f"Missing handling for node type {current_node.type}")

        if current_element:
            #if current_node
            style = ""

            px = 0
            py = 0
            #if not parent_container:

            #if current_node.type is NodeType.Text:
            #ss    style += "overflow: hidden; "


            if current_node.parent is not None and current_node.parent.layoutMode in [LayoutMode.Vertical,
                                                                                      LayoutMode.Horizontal]:
                absolute_position = False
                if current_node.parent.layoutMode == LayoutMode.Horizontal:
                    style += f"max-width: {current_node.absoluteBoundingBox.width}px; "
                    style += f"height: {current_node.absoluteBoundingBox.height}px; "
                if current_node.parent.layoutMode == LayoutMode.Vertical:
                    style += f"max-height: {current_node.absoluteBoundingBox.height}px; "
                    style += f"width: {current_node.absoluteBoundingBox.width}px; "
            elif parent_node is not None:
                py = parent_node.absoluteBoundingBox.y
                px = parent_node.absoluteBoundingBox.x

                if current_node.absoluteBoundingBox is not None and parent_node.absoluteBoundingBox is not None:
                    if current_node.constraints.vertical == Constraint.Top:
                         absolute_position = True
                    if current_node.constraints.horizontal == Constraint.Left:
                         absolute_position = True

            if absolute_position:
                style += (f"position: absolute; "
                          f"top: {current_node.absoluteBoundingBox.y-py}px; "
                          f"left: {current_node.absoluteBoundingBox.x-px}px; "
                          f"width: {current_node.absoluteBoundingBox.width}px; "
                          f"height: {current_node.absoluteBoundingBox.height}px; "
                          f"")

            if parent_node is None:
                style += (f"position: absolute; "
                          f"top: 0px; "
                          f"left: 0px; "
                          f"width: 1080px; "
                          f"height: 1920px; "
                          f"")



            if current_node.backgroundColor:
                style += (f"background-color: {FigmaRenderer.rgba_color(current_node.backgroundColor)}; ")
            if current_node.fills:
                if len(current_node.fills) == 1:
                    if current_node.fills[0].color:
                        style += f"color: {FigmaRenderer.rgba_color(current_node.fills[0].color)}; "
                else:
                    raise NotImplementedError(f"Unsupported count of fills {len(current_node.fills)}")
            if current_node.style is not None:
                print(current_node.name, current_node.style)
                text_style = ""
                current_node.style : StyleInfo
                if current_node.style.fontSize is not None:
                    text_style += f"font-size: {current_node.style.fontSize*0.95}px; "
                if current_node.style.textCase is TextCase.Upper:
                    text_style += f"text-transform: uppercase; "
                if current_node.style.fontFamily is not None:
                    text_style += f"font-family: {current_node.style.fontFamily}; "
                if current_node.style.fontStyle is not None:
                    text_style += f"font-style: {current_node.style.fontStyle}; "
                if current_node.style.fontWeight is not None:
                    text_style += f"font-weight: {current_node.style.fontWeight}; "
                if current_node.style.textDecoration is not None:
                    text_style += f"text-decoration: {current_node.style.textDecoration}; "
                if current_node.style.textAlignHorizontal is not None:
                    if current_node.style.textAlignHorizontal.lower() != "center":
                        text_style += f"text-align: {current_node.style.textAlignHorizontal}; width: 100%"
                    else:
                        text_style += f"text-align: center; "
                else:
                    text_style += f"text-align: center; "

                style += text_style
            if current_node.height:
                    style += f"min-height: {current_node.height}px; "
            if current_node.itemSpacing is not None:
                classes += f" gap-[{current_node.itemSpacing}px] "
                current_element.classes(classes)

            border_color = ""

            if current_node.strokes:
                for s in current_node.strokes:
                    print("stroke", current_node.name, current_node.characters, s.color)
                    border_color = FigmaRenderer.rgb_color(s.color)
                if current_node.individualStrokeWeights is None and current_node.strokeWeight:
                    style += f"border: {current_node.strokeWeight}px solid {border_color}; "

            #if current_node.strokeWeight:
            #    style += f"border: {current_node.strokeWeight}; "

            for css_key, value in (('padding-top', current_node.paddingTop),
                                   ('padding-bottom', current_node.paddingBottom),
                                   ('padding-left', current_node.paddingLeft),
                                   ('padding-right', current_node.paddingRight),
                                   ('border-top', f"{border_color} solid {current_node.individualStrokeWeights.top}" if current_node.individualStrokeWeights else None),
                                   ('border-bottom', f"{border_color} solid {current_node.individualStrokeWeights.bottom}" if current_node.individualStrokeWeights else None),
                                   ('border-left', f"{border_color} solid {current_node.individualStrokeWeights.left}" if current_node.individualStrokeWeights else None),
                                   ('border-right', f"{border_color} solid {current_node.individualStrokeWeights.right}" if current_node.individualStrokeWeights else None),
                                   ):
                if value is not None:
                    style += f"{css_key}: {value}px; "

            print("final style", current_node.name, style)
            current_element.style(style)
            current_node.ui_element = current_element
            return current_element

    @staticmethod
    def find_element(screen_data, filter) -> list[FigmaNode]:
        return findall(screen_data, filter_=filter)

    @staticmethod
    def find_exactly_one(screen_data, name : str) -> Optional[FigmaNode]:
        elements = findall(screen_data, filter_=lambda x: x.name == name)
        if elements:
            return elements[0]
        return None

    @staticmethod
    def maybe_find_one_label_child_of(screen_data, name : str, index=0) -> Optional[ui.label]:
        elements = findall(screen_data, filter_=lambda x: x.name == name)
        if elements:
            if elements[0].children:
                if len(elements[0].children) > index:
                    assert (type(elements[0].children[index].ui_element) == ui.label)
                    return elements[0].children[index].ui_element
        return None

    @staticmethod
    def find_all_starting_with(screen_data, name : str) -> list[FigmaNode]:
        return findall(screen_data, filter_=lambda x: x.name.startswith(name))


    def render_screen(self, page_name: str):
        if page_name not in self.all_screens:
            return
        screen_data = self.all_screens[page_name]
        ui.query('body').style(f'background-color: black; line-height: 1; ')
        context.client.content.classes('p-0').style(
            "min-height: 1936px;"
            "transform-origin: left top; "
            "transform: scale(var(--scale, 1)) translate(var(--offset, 0px), 0px);")
        footers = findall(screen_data, filter_=lambda x: x.name == "Footer")
        if len(footers) < 1:
            raise Exception("Failed to find Footer element")
        footer: FigmaNode = footers[0]
        footer.layoutMode = None
        footer.children[0].layoutMode = None
        footer.children[0].children[0].layoutMode = None
        footer.children[1].layoutMode = None
        root = FigmaRenderer.render_node(screen_data)
        root.style("min-height: 1936px;"
                   "border: 3px solid;"
                   "overflow: hidden; "
                   "border-color: white;")
        if footer.ui_element is not None:
            footer.ui_element.style("position: fixed; left: 0; bottom: 0; width: 1080px; ")
        return root, screen_data
