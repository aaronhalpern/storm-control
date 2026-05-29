import java.io.File;

import ij.IJ;
import ij.ImagePlus;
import ij.plugin.DragAndDrop;

public class Zarr_Drag_And_Drop extends DragAndDrop {

    public void openFile(File file) {
        if (isZarr(file)) {
            try {
                Object opened = IJ.runPlugIn("Zarr_Reader", normalizePath(file));
                if (opened instanceof ImagePlus) {
                    ImagePlus imp = (ImagePlus)opened;
                    if (imp.getWidth() > 0) imp.show();
                }
            }
            catch (Throwable t) {
                IJ.handleException(t);
            }
            return;
        }

        super.openFile(file);
    }

    private boolean isZarr(File file) {
        if (file == null || !file.exists()) return false;
        String name = file.getName().toLowerCase();
        if (file.isDirectory()) {
            return name.endsWith(".zarr") || new File(file, ".zgroup").exists() ||
                new File(file, ".zarray").exists() || new File(new File(file, "data"), ".zarray").exists();
        }
        return name.equals(".zarray");
    }

    private String normalizePath(File file) throws Exception {
        if (file.isFile() && file.getName().equals(".zarray")) {
            file = file.getParentFile();
        }
        return file.getCanonicalPath();
    }
}
