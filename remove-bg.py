#!/usr/bin/env python3
import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
gi.require_version('GimpUi', '3.0')
from gi.repository import GimpUi
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Gio
import sys
import tempfile
import subprocess

def N_(message): return message
def _(message): return GLib.dgettext(None, message)

PLUG_IN_PROC = 'python-fu-remove-bg'
GIMP_PLUGIN_ERROR = GLib.quark_from_string('gimp-plugin-error')

def check_and_install_rembg():
    try:
        import rembg
        return True, None
    except ImportError:
        try:
            # Ensure GTK3 is available for compatibility
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk

            dialog = GimpUi.Dialog(title=_("Install Required Package"))
            if hasattr(GimpUi, 'ResponseType'):
                dialog.add_button(_("_Cancel"), GimpUi.ResponseType.CANCEL)
                dialog.add_button(_("_Install"), GimpUi.ResponseType.OK)
                expected_response = GimpUi.ResponseType.OK
            else:
                dialog.add_button(_("_Cancel"), 0)
                dialog.add_button(_("_Install"), 1)
                expected_response = 1

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)  # Use Gtk.Box
            dialog.get_content_area().add(box)
            label = Gtk.Label(label=_("The 'rembg' package is required but not installed.\nWould you like to install it now?"))  # Gtk.Label
            label.set_line_wrap(True)
            box.add(label)

            dialog.show_all()
            response = dialog.run()
            dialog.destroy()

            if response != expected_response:
                return False, "Installation cancelled by user"

            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'rembg'])
            return True, None

        except subprocess.CalledProcessError as e:
            return False, f"Failed to install rembg: {str(e)}"
        except Exception as e:
            return False, f"Error during installation: {str(e)}"


def remove_background(procedure, run_mode, image, n_drawables, drawables, config, data):
    if run_mode == Gimp.RunMode.INTERACTIVE:
        GimpUi.init('python-fu-remove-bg')
        success, error_message = check_and_install_rembg()
        if not success:
            return procedure.new_return_values(
                Gimp.PDBStatusType.CALLING_ERROR,
                GLib.Error.new_literal(GIMP_PLUGIN_ERROR, error_message, 0)
            )

    try:
        from rembg import remove
    except ImportError:
         return procedure.new_return_values(
            Gimp.PDBStatusType.CALLING_ERROR,
            GLib.Error.new_literal(GIMP_PLUGIN_ERROR, "Failed to import rembg. Please install it.", 0) # More informative message
        )

    image.undo_group_start()

    try:
        for drawable in drawables:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_in, \
                 tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_out:

                Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, drawable, Gio.File.new_for_path(temp_in.name))

                with open(temp_in.name, 'rb') as i:
                    input_data = i.read()
                    output_data = remove(input_data)

                with open(temp_out.name, 'wb') as o:
                    o.write(output_data)

                new_layer = Gimp.File.load_layer(image, Gio.File.new_for_path(temp_out.name))
                new_name = f"{drawable.get_name()}-nobg"
                new_layer.set_name(new_name)

                parent = drawable.get_parent()
                position = image.get_item_position(drawable)
                image.insert_layer(new_layer, parent, position + 1) # Insert above, not replace


        Gimp.displays_flush()

    except Exception as e:
        error_message = f"Error during background removal: {str(e)}"
        image.undo_group_end()  # Ensure undo group ends even after error.
        return procedure.new_return_values(
            Gimp.PDBStatusType.EXECUTION_ERROR,
            GLib.Error.new_literal(GIMP_PLUGIN_ERROR, error_message, 0)
        )

    image.undo_group_end()
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)


class RemoveBG (Gimp.PlugIn):
    def do_set_i18n(self, procname):
        return True, 'gimp30-python', None

    def do_query_procedures(self):
        return [ PLUG_IN_PROC ]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, remove_background, None)
        procedure.set_image_types("RGB*, GRAY*")
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE | Gimp.ProcedureSensitivityMask.DRAWABLES)
        procedure.set_documentation (
            _("Remove background from selected layer(s)"),
            _("Creates new layer(s) with background removed using rembg. Will install rembg if needed."),
            name)
        procedure.set_menu_label(_("Remove _Background"))
        procedure.set_attribution("Assistant", "AI Assistant", "2024")
        procedure.add_menu_path("<Image>/Layer")
        return procedure

Gimp.main(RemoveBG.__gtype__, sys.argv)