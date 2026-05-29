// ImageJ/Fiji reader plugin for directory-based Zarr arrays and groups.
// Uses the N5/Zarr libraries bundled with Fiji.

import java.io.File;

import ij.IJ;
import ij.ImagePlus;
import ij.io.DirectoryChooser;
import ij.plugin.PlugIn;

import org.janelia.saalfeldlab.n5.N5Reader;
import org.janelia.saalfeldlab.n5.ij.N5IJUtils;
import org.janelia.saalfeldlab.n5.zarr.N5ZarrReader;

public class Zarr_Reader extends ImagePlus implements PlugIn {

    public void run(String arg) {
        String path = getPath(arg);
        if (path == null) return;
        if (!parse(path)) return;
        if (arg == null || arg.trim().length() == 0) this.show();
    }

    private String getPath(String arg) {
        if (arg != null && arg.trim().length() > 0) {
            File f = new File(arg);
            if (f.exists()) return normalizePath(f);
            if (arg.indexOf("://") > 0) return arg;
        }

        DirectoryChooser dc = new DirectoryChooser("Choose a .zarr folder");
        String dir = dc.getDirectory();
        if (dir == null) return null;
        return normalizePath(new File(dir));
    }

    private String normalizePath(File f) {
        if (f.isFile() && f.getName().equals(".zarray")) {
            f = f.getParentFile();
        }
        return f.getAbsolutePath();
    }

    private boolean parse(String path) {
        try {
            ImagePlus imp = openZarr(path);
            if (imp == null || imp.getWidth() == 0) {
                IJ.error("Zarr Reader", "Could not open Zarr data:\n" + path);
                return false;
            }

            this.setStack(imp.getTitle(), imp.getStack());
            this.setCalibration(imp.getCalibration());
            Object info = imp.getProperty("Info");
            if (info != null) this.setProperty("Info", info);
            if (imp.getOriginalFileInfo() != null) this.setFileInfo(imp.getOriginalFileInfo());
            this.setDimensions(imp.getNChannels(), imp.getNSlices(), imp.getNFrames());
            this.setOpenAsHyperStack(imp.getOpenAsHyperStack());
            return true;
        }
        catch (Throwable t) {
            IJ.handleException(t);
            return false;
        }
    }

    private ImagePlus openZarr(String path) throws Exception {
        configureBloscLibraryPath();
        N5Reader reader = new N5ZarrReader(path);
        String dataset = findDataset(reader, "");
        if (dataset == null) return null;
        return N5IJUtils.load(reader, dataset);
    }

    private void configureBloscLibraryPath() {
        String imagejDir = IJ.getDirectory("imagej");
        File nativeDir = imagejDir == null ? null : new File(new File(imagejDir, "lib"), "win64");
        if (nativeDir == null || !new File(nativeDir, "blosc.dll").exists()) {
            nativeDir = new File(new File(new File("Fiji.app"), "lib"), "win64");
        }
        if (!new File(nativeDir, "blosc.dll").exists()) return;

        String nativePath = nativeDir.getAbsolutePath();
        String current = System.getProperty("jna.library.path");
        if (current == null || current.length() == 0) {
            System.setProperty("jna.library.path", nativePath);
        }
        else if (current.indexOf(nativePath) < 0) {
            System.setProperty("jna.library.path", current + File.pathSeparator + nativePath);
        }
    }

    private String findDataset(N5Reader reader, String path) throws Exception {
        try {
            if (reader.datasetExists(path)) return path;
        }
        catch (Exception e) {
            // Continue into children when this path is a group or metadata is partial.
        }

        String[] children = reader.list(path);
        for (int i = 0; i < children.length; i++) {
            String childPath = path.length() == 0 ? children[i] : path + "/" + children[i];
            String dataset = findDataset(reader, childPath);
            if (dataset != null) return dataset;
        }
        return null;
    }
}
