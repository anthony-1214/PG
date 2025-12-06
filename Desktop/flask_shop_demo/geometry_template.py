# --- geometry_template.py ---
# (包含 直角三角形面積 模板 - 已移除中文)

from manim import *
from pathlib import Path
import math

# ==========================
# 🔧 模板共用設定
# ==========================
FONT = "Microsoft JhengHei" # 雖然改用英文，但保留字型設定以防萬一
def T(s, scale=1.0, color=WHITE): return Text(str(s), font=FONT).scale(scale).set_color(color) # Text 用戶端仍可能輸入中文

def fmt_num(x):
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.2f}"

# ==========================
# ✨ Helper 函式
# ==========================
TOL = 1e-6

def resolve_sides(sides):
    sides = list(map(float, sides))
    if len(sides) == 2:
        a, b = sides
        c = math.hypot(a, b)
        return a, b, c, False
    if len(sides) == 3:
        sides_sorted = sorted(sides)
        leg1, leg2, hyp = sides_sorted[0], sides_sorted[1], sides_sorted[2]
        if abs(hyp**2 - (leg1**2 + leg2**2)) <= TOL:
            return leg1, leg2, hyp, True
        c = math.hypot(leg1, leg2)
        print(f"⚠️ Warning: Input sides {sides} do not form a right triangle. Recalculated hypotenuse = {c:.3f}")
        return leg1, leg2, c, False
    raise ValueError("Input sides list must have length 2 or 3")


# ========= 視覺：TriangleAreaTemplate (已移除中文) =========
class TriangleAreaTemplate(Scene):
    def __init__(self,
                 sides=(3, 4, 5),
                 segments=None,
                 show_grid=False,
                 auto_scale=True,
                 max_visual_width=5.0,
                 max_visual_height=3.5,
                 color_rect = BLUE,
                 color_tri = YELLOW,
                 color_formula = WHITE,
                 color_result = GREEN,
                 **kwargs):
        super().__init__(**kwargs)

        try:
            self.leg_a, self.leg_b, self.hyp_c, self.hyp_given = resolve_sides(sides)
        except Exception as e:
             print(f"❌ Error resolving sides {sides}: {e}. Using default 3, 4, 5.")
             self.leg_a, self.leg_b, self.hyp_c, self.hyp_given = 3.0, 4.0, 5.0, True

        if segments:
            self.segments = [float(x) for x in segments]
        else:
            self.segments = [2.0, 2.0, 1.5, 2.5, 3.0]

        self.show_grid = show_grid

        self.scale_factor = 1.0
        if auto_scale and self.leg_a > 0 and self.leg_b > 0:
            scale_w = max_visual_width / self.leg_a
            scale_h = max_visual_height / self.leg_b
            self.scale_factor = min(scale_w, scale_h, 1.0)

        self.W = self.leg_a * self.scale_factor
        self.H = self.leg_b * self.scale_factor

        self.COLOR_RECT = color_rect
        self.COLOR_TRI = color_tri
        self.COLOR_FORMULA = color_formula
        self.COLOR_RESULT = color_result

    def _plan(self):
        default_times = [2.0, 2.0, 1.5, 2.5, 3.0]
        if not self.segments or len(self.segments) < 5:
             print(f"⚠️ Warning: Not enough segments ({len(self.segments)}), using default timings for TriangleAreaTemplate.")
             return default_times
        rt_rect, rt_rect_area, rt_split, rt_tri_area_derive = self.segments[0], self.segments[1], self.segments[2], self.segments[3]
        rt_formula_apply = sum(self.segments[4:])
        return [rt_rect, rt_rect_area, rt_split, rt_tri_area_derive, rt_formula_apply]

    def construct(self):
        rt_rect, rt_rect_area, rt_split, rt_tri_area_derive, rt_formula_apply = self._plan()

        if self.show_grid:
             grid = NumberPlane(
                x_range=[-7, 7, 0.5], y_range=[-4, 4, 0.5],
                axis_config={"stroke_color": TEAL, "stroke_width": 1.0, "include_tip": False},
                background_line_style={"stroke_color": GREY_B, "stroke_opacity": 0.5, "stroke_width": 0.6}
             ).set_opacity(0.5)
             self.add(grid)

        # --- 標題 (改英文) ---
        title = T("Right Triangle Area", scale=1.0).to_edge(UP)
        self.play(Write(title), run_time=0.5)
        rt_rect -= 0.5

        rect = Rectangle(width=self.W, height=self.H, color=self.COLOR_RECT)
        rect_center_pos = LEFT * (config.frame_width/4) + DOWN * 0.5
        rect.move_to(rect_center_pos)
        base_label = MathTex(fmt_num(self.leg_a)).next_to(rect.get_bottom(), DOWN, buff=0.2)
        height_label = MathTex(fmt_num(self.leg_b)).next_to(rect.get_left(), LEFT, buff=0.2)
        self.play(Create(rect), Write(VGroup(base_label, height_label)), run_time=max(1.0, rt_rect))

        # --- 長方形面積 (改英文) ---
        rect_area_text = T("Rectangle Area = Base x Height", scale=0.7).next_to(rect, RIGHT, buff=LARGE_BUFF).align_to(rect, UP)
        rect_area_calc = MathTex(f"= {fmt_num(self.leg_a)} \\times {fmt_num(self.leg_b)} = {fmt_num(self.leg_a * self.leg_b)}", font_size=36).next_to(rect_area_text, DOWN, aligned_edge=LEFT)
        self.play(Write(rect_area_text), Write(rect_area_calc), run_time=max(1.0, rt_rect_area))

        diagonal = Line(rect.get_corner(DL), rect.get_corner(UR), color=WHITE, stroke_width=3)
        self.play(Create(diagonal), run_time=max(0.5, rt_split*0.3))
        tri1 = Polygon(rect.get_corner(DL), rect.get_corner(DR), rect.get_corner(UR), color=self.COLOR_TRI, fill_opacity=0.6, stroke_width=1, stroke_color=self.COLOR_TRI)
        tri2 = Polygon(rect.get_corner(DL), rect.get_corner(UL), rect.get_corner(UR), color=self.COLOR_TRI, fill_opacity=0.0, stroke_width=1, stroke_color=WHITE)
        self.play(FadeIn(tri1), FadeIn(tri2), FadeOut(rect), run_time=max(0.5, rt_split*0.4))

        self.play(FadeOut(tri2), FadeOut(diagonal), run_time=max(0.5, rt_split*0.3))

        # --- 推導 (改英文) ---
        half_text = T("Triangle Area = Rectangle Area / 2", scale=0.7).move_to(rect_area_text)
        tri_area_calc_1 = MathTex(f"= {fmt_num(self.leg_a * self.leg_b)} \\div 2 = {fmt_num(0.5 * self.leg_a * self.leg_b)}", font_size=36).next_to(half_text, DOWN, aligned_edge=LEFT)
        self.play(Transform(rect_area_text, half_text), Transform(rect_area_calc, tri_area_calc_1), run_time=max(1.0, rt_tri_area_derive))

        self.play(FadeOut(rect_area_text), FadeOut(rect_area_calc), run_time=0.3)
        rt_formula_apply -= 0.3

        # --- 公式 (改英文 MathTex) ---
        # 使用 MathTex 和 \text{} 可以更好地處理空格和排版
        formula = MathTex("\\text{Area} = \\frac{1}{2} \\times \\text{base} \\times \\text{height}", font_size=36, color=self.COLOR_FORMULA)
        formula.move_to(rect_center_pos + RIGHT * (self.W/2 + LARGE_BUFF)).align_to(rect, UP)

        t_formula_write = max(0.5, rt_formula_apply * 0.2)
        t_indicate = max(0.8, rt_formula_apply * 0.2)
        t_substitute = max(0.8, rt_formula_apply * 0.3)
        t_calculate = max(0.8, rt_formula_apply * 0.3)

        self.play(Write(formula), run_time=t_formula_write)
        base_arrow = Arrow(formula.get_part_by_tex("base").get_bottom(), base_label.get_top(), buff=0.1, color=YELLOW)
        height_arrow = Arrow(formula.get_part_by_tex("height").get_left(), height_label.get_right(), buff=0.1, color=YELLOW)
        self.play(Create(base_arrow), Create(height_arrow), Indicate(base_label), Indicate(height_label), run_time=t_indicate)
        self.play(FadeOut(base_arrow), FadeOut(height_arrow))

        # --- 代入 (改英文 MathTex) ---
        formula_sub = MathTex(f"\\text{{Area}} = \\frac{{1}}{{2}} \\times {fmt_num(self.leg_a)} \\times {fmt_num(self.leg_b)}", font_size=36).move_to(formula)
        final_result = MathTex(f"= {fmt_num(0.5 * self.leg_a * self.leg_b)}", font_size=48, color=self.COLOR_RESULT).next_to(formula_sub, DOWN, buff=MED_LARGE_BUFF)
        final_box = SurroundingRectangle(final_result, color=self.COLOR_RESULT)

        self.play(TransformMatchingTex(formula, formula_sub), run_time=t_substitute)
        self.play(Write(final_result), Create(final_box), run_time=t_calculate)
        self.wait(1.5)