/**
 * PageNavigator - Simple pagination controls for multi-page documents.
 * Only renders when pageCount > 1.
 */
export default function PageNavigator({ currentPage, pageCount, onPageChange }) {
  if (!pageCount || pageCount <= 1) return null

  return (
    <div className="flex items-center justify-center gap-2 my-2">
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 0}
        className="px-2 py-1 text-sm border rounded disabled:opacity-30 hover:bg-gray-100"
      >
        &laquo; Prev
      </button>
      <span className="text-sm text-gray-600">
        Page {currentPage + 1} of {pageCount}
      </span>
      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage >= pageCount - 1}
        className="px-2 py-1 text-sm border rounded disabled:opacity-30 hover:bg-gray-100"
      >
        Next &raquo;
      </button>
    </div>
  )
}
