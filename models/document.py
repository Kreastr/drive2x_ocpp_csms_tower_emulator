"""

>>> import yaml
>>> dd = yaml.load(open("project.yaml"), Loader=yaml.SafeLoader)
>>> doc = FigmaNode.model_validate(dd)
>>> doc.update_parents()
"""
from enum import Enum
from typing import Optional, Literal, Any

from pydantic import BaseModel, Field, ConfigDict
from abc import ABCMeta
from anytree import NodeMixin

class ScrollBehavior(str, Enum):
    Scrolls = 'SCROLLS'

class StrokeAlign(str, Enum):
    Outside = 'OUTSIDE'
    Inside = 'INSIDE'
    Center = 'CENTER'

class BlendMode(str, Enum):
    PassThrough = 'PASS_THROUGH'

class LayoutWrap(str, Enum):
    NoWrap = 'NO_WRAP'

class LayoutSizing(str, Enum):
    Hug = 'HUG'
    Fixed = 'FIXED'
    Fill = 'FILL'

class LayoutMode(str, Enum):
    Vertical = 'VERTICAL'
    Horizontal = 'HORIZONTAL'

class LayoutAlign(str, Enum):
    Stretch = 'STRETCH'
    Inherit = 'INHERIT'

class AxisAlignItems(str, Enum):
    Center = 'CENTER'
    Max = 'MAX'
    SpaceBetween = 'SPACE_BETWEEN'

class AxisSizingMode(str, Enum):
    Fixed = 'FIXED'

class StrokeCap(str, Enum):
    Round = 'ROUND'

class StrokeJoin(str, Enum):
    Round = 'ROUND'

class Constraint(str, Enum):
    Center = 'CENTER'
    Top = 'TOP'
    Left = 'LEFT'
    Scale = 'SCALE'

class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    horizontal : Optional[Constraint] = None
    vertical: Optional[Constraint] = None

class NodeType(str, Enum):
    Document = 'DOCUMENT'
    Component = 'COMPONENT'
    ComponentSet = 'COMPONENT_SET'
    Canvas = 'CANVAS'
    Vector = 'VECTOR'
    Solid = 'SOLID'
    Instance = 'INSTANCE'
    Frame = 'FRAME'
    Text = 'TEXT'
    Group = 'GROUP'
    Ellipse = 'ELLIPSE'
    Rectangle = 'RECTANGLE'
    Line = 'LINE'
    Svg = 'SVG'


class Color(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a : float
    r : float
    g : float
    b : float


class ColorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blendMode: str
    color: Optional[Color] = None
    type : str
    visible : Optional[bool] = True
    imageRef : Optional[str] = None
    scaleMode : Optional[str] = None
    boundVariables : Optional[dict] = None

class TextCase(str, Enum):
    Upper = 'UPPER'

class RenderBounds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width : float
    height : float
    x : float
    y : float

class Sides(BaseModel):
    top : float
    bottom : float
    left : float
    right : float

class StyleInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fontFamily: Optional[str] = None
    fontPostScriptName: Optional[str] = None
    fontSize: Optional[float] = None
    fontStyle: Optional[str] = None
    fontWeight: Optional[int] = None
    letterSpacing: Optional[float] = None
    lineHeightPercent: Optional[float] = None
    lineHeightPx: Optional[float] = None
    lineHeightUnit: Optional[str] = None
    textAlignHorizontal: Optional[str] = None
    textAlignVertical: Optional[str] = None
    textAutoResize: Optional[str] = None
    textCase: Optional[TextCase] = None
    textDecoration : Optional[str] = None
    lineHeightPercentFontSize : Optional[float] = None
    italic : Optional[bool] = False
    textTruncation : Optional[str] = None

class FigmaNode(BaseModel, NodeMixin):
    model_config = ConfigDict(extra="forbid")

    figma_children : Optional[list['FigmaNode']] = Field(default_factory=list, validation_alias="children")
    backgroundColor : Optional[Color] = None
    prototypeBackgrounds : Optional[list[Color]] = Field(default_factory=list)
    scrollBehavior : Optional[str] = None
    characters : Optional[str] = None
    id : str
    name : str
    type : NodeType
    style : Optional[StyleInfo] = None
    styleOverrideTable : Optional[dict] = None
    prototypeDevice : Optional[dict] = None
    prototypeStartNodeID : Optional[str] = None
    flowStartingPoints : Optional[list] = None
    strokes : Optional[list[ColorInfo]] = None
    strokeWeight : Optional[float] = None
    strokeAlign : Optional[StrokeAlign] = None
    lineTypes : Optional[list] = None
    lineIndentations : Optional[list[int]] = None
    layoutVersion :  Optional[int] = None
    interactions : Optional[list] = None
    effects : Optional[list] = None
    fills : Optional[list[ColorInfo]] = None
    constraints : Optional[Constraints] = None
    blendMode : Optional[BlendMode] = None
    characterStyleOverrides : Optional[list] = None
    absoluteRenderBounds : Optional[RenderBounds] = None
    absoluteBoundingBox : Optional[RenderBounds] = None
    transitionEasing : Optional[str] = None
    transitionNodeID : Optional[str] = None
    transitionDuration : Optional[float] = None
    rotation : Optional[float] = None
    clipsContent : Optional[bool] = None
    background : Optional[list] = None
    boundVariables : Optional[dict] = None
    layoutWrap : Optional[LayoutWrap] = None
    layoutSizingVertical : Optional[LayoutSizing] = None
    layoutMode : Optional[LayoutMode] = None
    layoutSizingHorizontal : Optional[LayoutSizing] = None
    itemSpacing : Optional[float] = None
    paddingLeft : Optional[float] = None
    paddingRight: Optional[float] = None
    paddingTop: Optional[float] = None
    paddingBottom: Optional[float] = None
    marginLeft : Optional[float] = None
    marginRight: Optional[float] = None
    marginTop: Optional[float] = None
    marginBottom: Optional[float] = None
    layoutGrow : Optional[float] = None
    layoutAlign : Optional[LayoutAlign] = None
    targetAspectRatio : Optional[dict] = None
    componentId : Optional[str] = None
    componentProperties : Optional[dict] = None
    overrides : Optional[list] = None
    counterAxisAlignItems : Optional[AxisAlignItems] = None
    primaryAxisAlignItems : Optional[AxisAlignItems] = None
    counterAxisSizingMode : Optional[AxisSizingMode] = None
    primaryAxisSizingMode : Optional[AxisSizingMode] = None
    strokeCap : Optional[StrokeCap] = None
    strokeJoin : Optional[StrokeJoin] = None
    strokeMiterAngle : Optional[float] = None
    preserveRatio : Optional[bool] = None
    arcData : Optional[dict] = None
    cornerRadius : Optional[float] = None
    cornerSmoothing : Optional[float] = None
    styles : Optional[dict] = None
    individualStrokeWeights : Optional[Sides] = None
    fillOverrideTable : Optional[dict] = None
    visible : Optional[bool] = None
    componentPropertyDefinitions : Optional[dict] = None
    strokeDashes : Optional[list] = None
    opacity : Optional[float] = None
    rectangleCornerRadii : Optional[list] = None
    exportSettings: Optional[list] = None
    complexStrokeProperties : Optional[dict] = None

    _ui_element : Optional[Any] = None

    def __init__(self, *vargs, **kwargs):
        super(FigmaNode, self).__init__(*vargs, **kwargs)


    def update_parents(self, forced_svg : Optional[set]=None):
        if self.is_svg_candidate(forced_svg=forced_svg):
            self.type = NodeType.Svg
            self.figma_children = []
        else:
            self.children = self.figma_children
            for c in self.figma_children:
                c.parent = self
                c.update_parents(forced_svg=forced_svg)

    def is_svg_candidate(self, forced_svg : Optional[set]=None):
        if forced_svg is None:
            forced_svg = {}

        if self.name in forced_svg:
            return True

        if self.type not in [NodeType.Group, NodeType.Vector, NodeType.Ellipse, NodeType.Rectangle]:
            return False

        for c in self.figma_children:
            if not c.is_svg_candidate():
                return False

        return True
