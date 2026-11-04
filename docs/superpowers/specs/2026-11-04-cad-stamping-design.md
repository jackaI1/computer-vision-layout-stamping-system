# CAD drawing stamping

I want to keep the editable drawing when I stamp a sheet, rather than exporting
to PDF first. The existing browser and PDF placement pipeline stay available.

The CAD workflow is a Python command-line tool. It reads DXF with ezdxf, lists
sheet sizes, layer states and external drawing references, changes visibility,
binds references into local blocks, imports a vector seal from another drawing,
and inserts it on a dedicated layer in selected paper-space sheets. A PDF plot
uses the sheet's physical size and origin, including model-space viewports.
Coordinates and seal diameter are in each sheet's paper units, with explicit
positions instead of an unverified automatic collision search.

## Approaches

Adding DXF uploads to the PDF UI would discard editable CAD output. Driving a
licensed AutoCAD installation would make the public example hard to repeat.
I choose an ezdxf CLI alongside the PDF app: it supports editable copies and
headless checks. DWG uses the freely downloadable ODA File Converter, separately
installed, with a clear error when absent. This is an implementation choice
under the owner's instruction to finish without questions.

## Contracts

- Source files and existing outputs are never overwritten by CLI commands.
- Reference paths resolve relative to their own drawing, then explicit search
  folders. Nested references bind bottom-up; missing files and cycles fail.
  Nested overlays do not propagate into a referenced drawing.
- Layer names are checked, visibility changes survive save/reopen, and the seal
  INSERT belongs to STAMPER_SEAL. Repeat stamping replaces only tool-owned seals.
- A seal DXF supplies vector geometry in model space, normalized to the requested
  diameter. Date and caption travel in the same reusable block. No real seals,
  signatures or client files are included.
- Plotting refuses unresolved references and unsupported perspective/tilted
  viewports rather than silently publishing incomplete sheets. PDF plots are
  review output, not an AutoCAD plot-style or professional approval substitute.
- Generated examples include a floor plan, referenced furniture, two sheet
  layouts, and a clearly marked demonstration seal. CI runs old and new tests
  plus a complete sample command sequence.

More complex 3D views, CTB/STB plot styles, automatic CAD whitespace placement,
and production professional approval are outside this change.
