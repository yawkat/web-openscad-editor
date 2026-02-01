// web-openscad-editor example
//
// This file is meant to exercise the generator + OpenSCAD customizer parsing.

/* [Model] */

shape = "rounded box"; // [rounded box, capsule, ring]

width = 60; // [10:1:140]
depth = 40; // [10:1:140]
height = 20; // [5:1:80]

rounding = 6; // [0:0.5:30]

hole_diameter = 6; // [0:0.5:30]
hole_count = 6; // [0:1:24]

show_baseplate = true;
baseplate_thickness = 2; // [0:0.5:10]

show_text = true;
text_string = "web-openscad-editor";
text_font = "DejaVu Sans:style=Bold";
text_size = 8; // [2:0.5:24]
text_depth = 1.2; // [0.2:0.1:5]
text_z_offset = 0.2; // [-2:0.1:4]
text_anchor = "center"; // [center, left, right]

/* [Hidden] */

$fn = 72;

module rounded_box(w, d, h, r) {
  // 2D offset + extrude keeps this reasonably fast.
  r2 = max(0, r);
  wi = max(0.01, w - 2 * r2);
  di = max(0.01, d - 2 * r2);
  linear_extrude(height = h)
    offset(r = r2)
      square([wi, di], center = true);
}

module capsule(w, d, h) {
  // A simple pill/capsule shape (hull of two cylinders).
  rr = min(w, d) / 2;
  hull() {
    translate([-(w / 2 - rr), 0, 0]) cylinder(r = rr, h = h);
    translate([+(w / 2 - rr), 0, 0]) cylinder(r = rr, h = h);
  }
}

module ring(od, id, h) {
  difference() {
    cylinder(d = od, h = h);
    if (id > 0)
      translate([0, 0, -0.1]) cylinder(d = id, h = h + 0.2);
  }
}

module bolt_holes(count, d, r, h) {
  if (count <= 0 || d <= 0)
    ;
  else
    for (i = [0 : count - 1])
      rotate([0, 0, i * 360 / count])
        translate([r, 0, -0.1])
          cylinder(d = d, h = h + 0.2);
}

module label_3d(str, font, size, depth, anchor) {
  // Use fontconfig-backed text() rendering.
  // If fonts are not available in the WASM build, this will warn about missing fonts.
  // We extrude slightly to make it visible in the exported mesh.
  linear_extrude(height = depth)
    text(
      text = str,
      size = size,
      font = font,
      halign = anchor,
      valign = "center",
      $fn = 24
    );
}

model_h = height;

difference() {
  union() {
    if (shape == "rounded box")
      rounded_box(width, depth, model_h, rounding);
    else if (shape == "capsule")
      capsule(width, depth, model_h);
    else
      ring(min(width, depth), min(width, depth) * 0.6, model_h);

    if (show_baseplate && baseplate_thickness > 0)
      translate([0, 0, -baseplate_thickness])
        rounded_box(width * 1.1, depth * 1.1, baseplate_thickness, rounding);

    if (show_text) {
      // Put text on the top face.
      translate([0, 0, model_h + text_z_offset])
        label_3d(text_string, text_font, text_size, text_depth, text_anchor);
    }
  }

  bolt_holes(hole_count, hole_diameter, min(width, depth) * 0.35, model_h)
    ;
}
